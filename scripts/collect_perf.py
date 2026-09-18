"""주간 성과 수집 — YouTube Analytics API → data/perf.csv, 주제별 가중치 갱신 → data/state.json

지표: 영상별 조회수, 평균 시청 비율(%), 구독 증가, 좋아요. (스와이프 유지율은 API 미제공 → 시청 비율로 대체)
가중치 규칙: 주제별 평균 시청비율 상위 = ×1.5, 하위 = ×0.5, [0.25, 4.0]로 클램프. 표본 3편 미만이면 유지.
"""
import csv
import json
import os
from datetime import date, timedelta
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
PERF = ROOT / "data" / "perf.csv"
SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly",
          "https://www.googleapis.com/auth/youtube.readonly"]


def creds():
    return Credentials(None, refresh_token=os.environ["YT_REFRESH_TOKEN"],
                       client_id=os.environ["YT_CLIENT_ID"], client_secret=os.environ["YT_CLIENT_SECRET"],
                       token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES)


def main() -> None:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    vids = {h["video_id"]: h for h in state["history"] if h.get("video_id")}
    if not vids:
        print("no uploaded videos yet")
        return
    ya = build("youtubeAnalytics", "v2", credentials=creds(), cache_discovery=False)
    end, start = date.today(), date.today() - timedelta(days=28)
    rows = []
    for chunk in [list(vids)[i:i + 50] for i in range(0, len(vids), 50)]:
        r = ya.reports().query(
            ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(),
            metrics="views,averageViewPercentage,subscribersGained,likes",
            dimensions="video", filters="video==" + ",".join(chunk)).execute()
        for vid, views, avp, subs, likes in r.get("rows", []):
            h = vids[vid]
            rows.append({"collected": end.isoformat(), "video_id": vid, "date": h["date"],
                         "topic_id": h["topic_id"], "template": h.get("template"),
                         "views": int(views), "avg_view_pct": round(float(avp), 1),
                         "subs_gained": int(subs), "likes": int(likes)})
    if not rows:
        print("no analytics rows")
        return
    new = not PERF.exists()
    with open(PERF, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if new:
            w.writeheader()
        w.writerows(rows)

    # 주제별 가중치 갱신
    by_topic: dict[str, list[float]] = {}
    for r in rows:
        by_topic.setdefault(r["topic_id"], []).append(r["avg_view_pct"])
    scored = {t: sum(v) / len(v) for t, v in by_topic.items() if len(v) >= 3}
    if len(scored) >= 2:
        ranked = sorted(scored, key=scored.get)
        lo, hi = ranked[: max(1, len(ranked) // 3)], ranked[-max(1, len(ranked) // 3):]
        w = state.setdefault("weights", {})
        for t in hi:
            w[t] = min(4.0, w.get(t, 1.0) * 1.5)
        for t in lo:
            w[t] = max(0.25, w.get(t, 1.0) * 0.5)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    top = sorted(rows, key=lambda r: -r["views"])[:3]
    bottom = sorted(rows, key=lambda r: r["views"])[:3]
    msg = ["[shorts] 주간 성과 요약",
           "상위: " + " / ".join(f"{r['topic_id']} {r['views']:,}회 {r['avg_view_pct']}%" for r in top),
           "하위: " + " / ".join(f"{r['topic_id']} {r['views']:,}회 {r['avg_view_pct']}%" for r in bottom),
           "가중치: " + json.dumps(state.get("weights", {}), ensure_ascii=False)]
    from shorts.notify import send  # noqa: E402
    send("\n".join(msg))


if __name__ == "__main__":
    main()
