"""주제 선별 — 변동률·가중치·연속 업로드 제한·이상치 규칙."""
import json
from datetime import date
from .config import STATE_PATH


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"history": [], "weights": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def uploads_today(state: dict) -> int:
    today = date.today().isoformat()
    return sum(1 for h in state["history"] if h["date"] == today and h.get("uploaded"))


def _streak(state: dict, topic_id: str) -> int:
    n = 0
    for h in reversed(state["history"]):
        if h["topic_id"] == topic_id:
            n += 1
        else:
            break
    return n


def select(topics: list[dict], state: dict, safety: dict) -> tuple[dict | None, str]:
    """(선택된 주제, 사유). 선택 불가 시 (None, 사유)."""
    cands = []
    for t in topics:
        chg = abs(t["change_pct"])
        if chg >= safety["anomaly_change_pct"]:
            return None, f"이상치 감지: {t['id']} {t['change_pct']:+.1f}% — 데이터 확인 필요"
        if chg < safety["min_change_pct_to_post"]:
            continue
        if _streak(state, t["id"]) >= safety["same_topic_max_streak"]:
            continue
        w = state["weights"].get(t["id"], 1.0)
        cands.append((chg * w, t))
    if not cands:
        return None, "게시 기준을 넘는 변동이 있는 주제가 없음 (오늘은 건너뜀)"
    cands.sort(key=lambda x: -x[0])
    return cands[0][1], f"score={cands[0][0]:.2f}"
