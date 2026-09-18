"""대본 생성 — 수치는 코드(insights)가 계산하고, LLM은 문장만 다듬는다."""
import json
import os
import re

SYSTEM = """당신은 한국어 데이터 해설 숏폼 대본 작가입니다.
규칙:
- 주어진 '훅'과 '사실 문장'에 있는 숫자만 사용하세요. 새로운 숫자를 만들지 마세요.
- 첫 문장은 주어진 훅의 의미를 유지하되 더 자연스럽게 다듬으세요. 2초 안에 읽혀야 합니다.
- 예측, 전망, 투자 판단 문장을 절대 쓰지 마세요. "오를 것", "사야", "기회" 같은 표현 금지.
- 전체 6~8문장, 낭독 35~45초, 문장당 25자 내외. 구어체.
- 주어진 '정리'와 '다음 예고' 문장은 반드시 마지막 두 문장으로 그대로 유지하세요(다듬는 것은 허용).
- 훅에서 던진 질문의 답이 '정리' 바로 앞에 오도록 순서를 지키세요.
- 감정 자극 표현(충격, 폭락, 망했다) 금지. 사실과 맥락만.
반드시 JSON으로만 답하세요: {"title": "...", "lines": ["...", "..."]}
title은 35자 이내, 궁금증을 남기되 낚시성 표현은 쓰지 마세요."""

TAG_MAP = {
    "코스피": ["#코스피", "#증시"],
    "코스닥": ["#코스닥", "#증시"],
    "유가": ["#유가", "#원자재"],
    "금값": ["#금값", "#원자재"],
    "환율": ["#환율", "#경제"],
}

CLOSING = "내일도 숫자 하나로 정리해 드립니다."


def _assemble(insight) -> list[str]:
    """훅 → 근거 → 가져갈 한 줄 → 다음에 볼 이유. 마무리 두 줄이 '그래서 어쩌라고'를 막는다."""
    lines = [insight.hook] + list(insight.body)
    if insight.takeaway:
        lines.append(insight.takeaway)
    lines.append(insight.next_line or CLOSING)
    return lines


SEC_PER_CHAR = 0.16     # edge-tts ko-KR, rate +8% 실측 기준
SEC_PER_PAUSE = 0.25


def _split_sentences(lines: list[str]) -> list[str]:
    """한 줄에 두 문장이 있으면 나눈다. 자막 한 장에는 한 문장만 올라가야 읽힌다."""
    out = []
    for ln in lines:
        parts = [x.strip() for x in re.split(r"(?<=다\.)\s+", ln) if x.strip()]
        out.extend(parts or [ln])
    return out


def _est_sec(lines: list[str]) -> float:
    return sum(len(l) for l in lines) * SEC_PER_CHAR + len(lines) * SEC_PER_PAUSE


def _fit(lines: list[str], max_sec: float, keep_tail: int = 2) -> list[str]:
    """길이 초과 시 근거 문장만 뒤에서부터 덜어낸다. 훅과 마무리 두 줄은 절대 건드리지 않는다."""
    out = list(lines)
    # 훅 1 + 근거 최소 3 + 마무리 = 바닥. 더 줄이면 훅의 답까지 사라진다.
    floor = 1 + 3 + keep_tail
    while _est_sec(out) > max_sec and len(out) > floor:
        del out[-(keep_tail + 1)]          # 마무리 직전 = 가장 덜 중요한 부연
    return out


def _tags(topic: dict) -> list[str]:
    """소스가 지정한 태그를 우선하고, 없으면 주제명에서 유추한다."""
    if topic.get("hashtags"):
        return topic["hashtags"]
    kw = topic.get("title_kw", "")
    for k, v in TAG_MAP.items():
        if k in kw:
            return v + ["#오늘의숫자"]
    return ["#데이터", "#경제", "#오늘의숫자"]


def _clean_title(title: str, banned: list[str]) -> str:
    for w in banned:
        title = title.replace(w, "")
    return re.sub(r"\s+", " ", title).strip()[:60]


def _fallback(topic: dict, insight) -> dict:
    """LLM 없이도 성립하는 대본. 인사이트가 있으면 그것이 뼈대가 된다."""
    if insight:
        lines = _assemble(insight)
        title = insight.title or insight.hook
    else:
        lines = [f"{topic['title_kw']}, 오늘 {topic['latest']:,.2f}{topic['unit']}입니다."] \
            + topic["context"][1:] + [CLOSING]
        title = f"{topic['title_kw']} 오늘 {topic['change_pct']:+.1f}%, 무슨 일이 있었나"
        lines = lines[:8]
    return {"title": title, "lines": lines}   # 인사이트 대본은 자르지 않는다 (마무리 두 줄 보호)


def generate(topic: dict, llm_cfg: dict, banned: list[str], insight=None, max_sec: float = 50.0) -> dict:
    provider = llm_cfg.get("provider", "none")
    key = os.getenv("ANTHROPIC_API_KEY")

    if provider != "anthropic" or not key:
        out = _fallback(topic, insight)
    else:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            if insight:
                user = (f"주제: {topic['title_kw']}\n"
                        f"훅: {insight.hook}\n"
                        f"사실 문장:\n- " + "\n- ".join(insight.body) +
                        f"\n\n정리(끝에서 두 번째): {insight.takeaway}"
                        f"\n다음 예고(마지막): {insight.next_line}"
                        f"\n\n참고 수치:\n- " + "\n- ".join(topic["context"]))
            else:
                user = f"주제: {topic['title_kw']}\n사실 문장:\n- " + "\n- ".join(topic["context"])
            msg = client.messages.create(
                model=llm_cfg.get("model", "claude-haiku-4-5"),
                max_tokens=llm_cfg.get("max_tokens", 500),
                system=SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = msg.content[0].text
            out = json.loads(text[text.find("{"): text.rfind("}") + 1])
            assert out["lines"] and out["title"]
        except Exception as e:
            print(f"[llm] fallback: {e}")
            out = _fallback(topic, insight)

    out["title"] = _clean_title(out["title"], banned)
    lines = [l.strip() for l in out["lines"] if l.strip()][:10]
    # 마무리 두 줄이 빠지면 강제로 복원한다 (LLM이 잘라먹는 경우 대비)
    if insight and lines:
        tail = " ".join(lines[-2:])
        if insight.next_line and insight.next_line[:12] not in tail:
            lines.append(insight.next_line)
    elif lines and CLOSING not in lines[-1]:
        lines.append(CLOSING)

    lines = _split_sentences(lines)
    before = _est_sec(lines)
    lines = _fit(lines, max_sec, keep_tail=2 if insight else 1)
    if len(lines) != len(out["lines"]):
        print(f"[script] 길이 조정: {before:.0f}초 -> {_est_sec(lines):.0f}초 (상한 {max_sec:.0f}초)")
    out["lines"] = lines
    out["hashtags"] = _tags(topic)          # LLM이 엉뚱한 태그를 붙이는 것 방지
    out["insight_kind"] = insight.kind if insight else "none"
    # 훅 카드용 — 렌더러가 첫 화면에 크게 띄운다
    out["big"] = insight.big if insight else ""
    out["hook"] = lines[0] if lines else (insight.hook if insight else "")
    return out
