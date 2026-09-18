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
- 마지막 문장은 "내일도 숫자 하나로 정리해 드립니다." 로 끝냅니다.
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
        lines = [insight.hook] + insight.body + [CLOSING]
        title = insight.title or insight.hook
    else:
        lines = [f"{topic['title_kw']}, 오늘 {topic['latest']:,.2f}{topic['unit']}입니다."] \
            + topic["context"][1:] + [CLOSING]
        title = f"{topic['title_kw']} 오늘 {topic['change_pct']:+.1f}%, 무슨 일이 있었나"
    return {"title": title, "lines": lines[:8]}


def generate(topic: dict, llm_cfg: dict, banned: list[str], insight=None) -> dict:
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
    lines = [l.strip() for l in out["lines"] if l.strip()][:8]
    if lines and CLOSING not in lines[-1]:
        lines.append(CLOSING)
    out["lines"] = lines
    out["hashtags"] = _tags(topic)          # LLM이 엉뚱한 태그를 붙이는 것 방지
    out["insight_kind"] = insight.kind if insight else "none"
    return out
