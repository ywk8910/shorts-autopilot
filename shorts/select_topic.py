"""주제 선별 — 변동성 대비 희귀도(z), 최근 등장 빈도, 연속 제한, 이상치 규칙.

왜 z로 비교하나:
원래는 |전일 대비 %|로만 순위를 매겼다. 그러면 변동성이 큰 유가가 구조적으로
매일 이긴다(실측: 14일 중 9일 64%가 유가, 환율은 0회). 코스피 2% 움직임과
유가 2% 움직임은 같은 사건이 아니므로, 각 지표 자신의 일간 변동 표준편차로
나눠 "그 지표 기준으로 얼마나 드문 날인가"를 비교한다.
"""
import json
import statistics
from datetime import datetime, timedelta, timezone
from .config import STATE_PATH

RECENT_WINDOW = 7          # 최근 몇 편을 보고 편중을 판단할지
REPEAT_PENALTY = 0.5       # 최근 창에서 1회 등장할 때마다 점수를 나누는 정도

KST = timezone(timedelta(hours=9))


def today_kst() -> str:
    """하루의 경계는 KST 기준.

    러너는 UTC로 돌고 GitHub 스케줄러는 cron 시각보다 2~4시간 늦게 뜬다.
    그래서 date.today()(UTC)로 찍으면 어떤 실행은 23:4x Z, 다음 실행은 00:0x Z가 되어
    같은 UTC 날짜에 두 번 기록되거나 하루가 통째로 비어 보인다(실측: 10/03이 2건).
    """
    return datetime.now(KST).date().isoformat()


def _produced(h: dict) -> bool:
    """이 기록이 실제로 영상을 만들었나. 건너뛴 날은 topic_id가 None이다.

    업로드 여부로 판단하면 안 된다. 검수 대기 중(upload_enabled=false)에는
    uploaded가 항상 False라서 하루 상한도, 편중 감점도 통째로 꺼진다.
    """
    return h.get("topic_id") is not None


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"history": [], "weights": {}}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def uploads_today(state: dict) -> int:
    """오늘(KST) 이미 영상을 만든 횟수. 업로드 여부와 무관하다."""
    today = today_kst()
    return sum(1 for h in state["history"] if h["date"] == today and _produced(h))


def _streak(state: dict, topic_id: str) -> int:
    n = 0
    for h in reversed(state["history"]):
        if h["topic_id"] == topic_id:
            n += 1
        else:
            break
    return n


def _recent_count(state: dict, topic_id: str) -> int:
    """최근 만든 RECENT_WINDOW편 중 이 주제가 몇 번 나왔나."""
    recent = [h["topic_id"] for h in state["history"] if _produced(h)][-RECENT_WINDOW:]
    return recent.count(topic_id)


def zscore(topic: dict) -> float:
    """오늘 변동률 ÷ 이 지표의 일간 변동 표준편차. 표본이 부족하면 1.0으로 중립 처리."""
    s = topic.get("long") or topic["series"]
    if len(s) < 31:
        return 1.0
    ch = [(s[i][1] / s[i - 1][1] - 1) * 100 for i in range(1, len(s))]
    sd = statistics.pstdev(ch)
    if sd <= 0:
        return 0.0
    return abs(topic["change_pct"]) / sd


def select(topics: list[dict], state: dict, safety: dict) -> tuple[dict | None, str]:
    """(선택된 주제, 사유). 선택 불가 시 (None, 사유)."""
    min_z = safety.get("min_z_to_post", 1.0)
    min_abs = safety.get("min_change_pct_to_post", 0.2)

    cands, log = [], []
    for t in topics:
        chg = abs(t["change_pct"])
        if chg >= safety["anomaly_change_pct"]:
            return None, f"이상치 감지: {t['id']} {t['change_pct']:+.1f}% — 데이터 확인 필요"

        z = zscore(t)
        if z < min_z or chg < min_abs:          # 평범한 날이거나 움직임 자체가 미미
            continue
        if _streak(state, t["id"]) >= safety["same_topic_max_streak"]:
            continue

        w = state["weights"].get(t["id"], 1.0)
        rep = _recent_count(state, t["id"])
        score = z * w / (1 + REPEAT_PENALTY * rep)   # 최근에 자주 나온 주제는 감점
        cands.append((score, t))
        log.append(f"{t['id']}:z{z:.1f}" + (f"/최근{rep}회" if rep else ""))

    if not cands:
        return None, f"기준(z≥{min_z}, |변동|≥{min_abs}%)을 넘는 주제가 없음 (오늘은 건너뜀)"

    cands.sort(key=lambda x: -x[0])
    print("[select] " + ", ".join(log))
    best = cands[0]
    return best[1], f"score={best[0]:.2f} (z={zscore(best[1]):.1f})"
