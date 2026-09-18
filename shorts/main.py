"""엔트리포인트: python -m shorts.main [--dry-run] [--silent-tts] [--template line|counter]

흐름: 소스 수집 → 주제 선별 → 대본 → TTS → 렌더 → (업로드) → 상태 저장 → 알림
"""
import argparse
import json
import shutil
from datetime import date

from . import config as C
from .sources import fetch_all
from .select_topic import load_state, save_state, select, uploads_today
from .script_gen import generate
from .insights import pick as pick_insight
from .tts import synthesize, concat
from .render import render
from .notify import send


def pick_template(state: dict, templates: list[str]) -> str:
    n = len(state["history"])
    return templates[n % len(templates)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="업로드 생략")
    ap.add_argument("--silent-tts", action="store_true", help="TTS 대신 무음 (오프라인 테스트)")
    ap.add_argument("--template", default=None)
    ap.add_argument("--force", action="store_true", help="게시 기준(변동률·연속) 무시")
    args = ap.parse_args()

    cfg = C.load()
    state = load_state()
    today = date.today().isoformat()

    if uploads_today(state) >= cfg["channel"]["max_uploads_per_day"] and not args.force:
        send(f"[shorts] {today} 오늘 업로드 상한 도달, 종료")
        return 0

    topics = fetch_all(cfg["sources"])
    if not topics:
        send(f"[shorts] {today} 모든 데이터 소스 실패 — 확인 필요")
        return 1

    safety = dict(cfg["safety"])
    if args.force:
        safety["min_change_pct_to_post"] = -1
        safety["same_topic_max_streak"] = 99
    topic, why = select(topics, state, safety)
    if topic is None:
        send(f"[shorts] {today} 건너뜀: {why}")
        state["history"].append({"date": today, "topic_id": None, "uploaded": False, "reason": why})
        save_state(state)
        return 0

    recent_kinds = [h.get("insight_kind", "none") for h in state["history"] if h.get("uploaded")]
    insight = pick_insight(topic, topics, recent_kinds)
    if insight:
        print(f"[insight] 선택: {insight.kind} ({insight.score:.0f}점)")
    else:
        print("[insight] 발동한 탐지기 없음 — 현황 서술로 대체")

    script = generate(topic, cfg["llm"], cfg["safety"]["banned_title_words"], insight=insight)
    print(json.dumps(script, ensure_ascii=False, indent=2))

    work = C.OUT_DIR / "work"
    if work.exists():
        shutil.rmtree(work)
    segs = synthesize(script["lines"], work, cfg["voice"], silent=args.silent_tts)
    audio = concat(segs, work / "voice.mp3")

    template = args.template or pick_template(state, cfg["video"]["templates"])
    out_mp4 = C.OUT_DIR / f"{today}_{topic['id']}.mp4"
    render(topic, script, segs, audio, out_mp4, cfg["video"], template=template)
    print(f"rendered: {out_mp4} ({template}, {sum(s['dur'] for s in segs):.1f}s)")

    video_id, uploaded = None, False
    if not args.dry_run:
        from .upload import upload
        desc = "\n".join(script["lines"]) + f"\n\n출처: {topic['source_name']} {topic['source_url']}\n" \
               f"기준일: {topic['series'][-1][0]}\n음성은 AI 합성입니다.\n" + " ".join(script["hashtags"])
        video_id = upload(out_mp4, script["title"], desc,
                          cfg["channel"]["default_tags"] + [h.lstrip("#") for h in script["hashtags"]],
                          cfg["channel"])
        uploaded = True

    state["history"].append({"date": today, "topic_id": topic["id"], "template": template,
                             "insight_kind": script.get("insight_kind", "none"),
                             "title": script["title"], "video_id": video_id, "uploaded": uploaded,
                             "change_pct": round(topic["change_pct"], 3)})
    save_state(state)
    send(f"[shorts] {today} {'업로드 완료' if uploaded else '생성만 완료(dry-run)'}\n"
         f"제목: {script['title']}\n"
         f"주제: {topic['id']} ({topic['change_pct']:+.2f}%) / 인사이트 {script.get('insight_kind')} / 템플릿 {template}\n"
         + (f"https://youtube.com/shorts/{video_id}" if video_id else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
