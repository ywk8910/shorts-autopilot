"""대본 생성 — 수치는 코드가 계산한 context 문장만 사용, LLM은 문장 재구성만 담당."""
import json
import os
import re

SYSTEM = """당신은 한국어 데이터 해설 숏폼 대본 작가입니다.
규칙:
- 주어진 '사실 문장'에 있는 숫자만 사용하고, 새로운 숫자·예측·투자 조언을 절대 만들지 마세요.
- 첫 문장은 2초 안에 읽히는 훅(숫자 또는 질문)으로 시작합니다.
- 전체 5~7문장, 낭독 시 35~45초 분량, 문장당 25자 내외.
- 마지막 문장은 "내일도 숫자 하나로 정리해 드립니다." 로 끝냅니다.
- 감정 자극 표현(충격, 폭락, 망했다 등) 금지. 사실과 맥락만.
반드시 JSON으로만 답하세요: {"title": "...", "lines": ["...", "..."], "hashtags": ["#..", "#.."]}
title은 35자 이내, 질문형 또는 숫자 포함형."""


TAG_MAP = {
    "코스피": ["#코스피", "#증시"],
    "코스닥": ["#코스닥", "#증시"],
    "유가": ["#유가", "#원자재"],
    "금값": ["#금값", "#원자재"],
    "환율": ["#환율", "#경제"],
}


def _tags(topic: dict) -> list[str]:
    """소스가 지정한 태그를 우선하고, 없으면 주제명에서 유추한다."""
    if topic.get("hashtags"):
        return topic["hashtags"]
    kw = topic.get("title_kw", "")
    for k, v in TAG_MAP.items():
        if k in kw:
            return v + ["#오늘의숫자"]
    return ["#데이터", "#경제", "#오늘의숫자"]


def _fallback(topic: dict) -> dict:
    ctx = topic["context"]
    lines = [f"{topic['title_kw']}, 오늘 {topic['latest']:,.2f}{topic['unit']}입니다."] + ctx[1:] + [
        "내일도 숫자 하나로 정리해 드립니다."]
    return {
        "title": f"{topic['title_kw']} 오늘 {topic['change_pct']:+.1f}%, 무슨 일이 있었나",
        "lines": lines[:7],
        "hashtags": _tags(topic),
    }


def _clean_title(title: str, banned: list[str]) -> str:
    for w in banned:
        title = title.replace(w, "")
    return re.sub(r"\s+", " ", title).strip()[:60]


def generate(topic: dict, llm_cfg: dict, banned: list[str]) -> dict:
    provider = llm_cfg.get("provider", "none")
    key = os.getenv("ANTHROPIC_API_KEY")
    if provider != "anthropic" or not key:
        out = _fallback(topic)
    else:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            user = "주제: " + topic["title_kw"] + "\n사실 문장:\n- " + "\n- ".join(topic["context"])
            msg = client.messages.create(
                model=llm_cfg.get("model", "claude-haiku-4-5"),
                max_tokens=llm_cfg.get("max_tokens", 400),
                system=SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
            text = msg.content[0].text
            out = json.loads(text[text.find("{"): text.rfind("}") + 1])
            assert out["lines"] and out["title"]
        except Exception as e:
            print(f"[llm] fallback: {e}")
            out = _fallback(topic)
    out["title"] = _clean_title(out["title"], banned)
    out["lines"] = [l.strip() for l in out["lines"] if l.strip()][:8]
    out["hashtags"] = _tags(topic)   # LLM이 엉뚱한 태그를 붙이는 것 방지
    return out
