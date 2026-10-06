"""엔트리포인트: python -m shorts.main [--dry-run] [--silent-tts] [--template line|counter]

흐름: 소스 수집 → 주제 선별 → 대본 → TTS → 렌더 → (업로드) → 상태 저장 → 알림
"""
import argparse
import json
import os
import shutil

from . import config as C
from .sources import fetch_all
from .select_topic import load_state, save_state, select, uploads_today, today_kst
from .script_gen import generate
from .insights import pick as pick_insight
from .tts import synthesize, concat
from .render import render
from .notify import send


RELEASE_TAG_PREFIX = "short-"


def pick_template(state: dict, templates: list[str]) -> str:
    n = len(state["history"])
    return templates[n % len(templates)]


def build_description(script: dict, topic: dict) -> str:
    """YouTube 설명란에 그대로 들어갈 본문. 업로드를 자동으로 하든 손으로 하든 같은 글이다."""
    return ("\n".join(script["lines"])
            + f"\n\n출처: {topic['source_name']} {topic['source_url']}\n"
            + f"기준일: {topic['series'][-1][0]}\n음성은 AI 합성입니다.\n"
            + " ".join(script["hashtags"]))


def download_url(today: str, filename: str) -> str:
    """Release 자산 주소는 태그와 파일명만으로 정해진다.

    덕분에 Release를 만들기 전인 이 시점에도 알림에 링크를 넣을 수 있다.
    (Release는 영상 생성 뒤 워크플로가 만든다.)
    """
    repo = os.getenv("GITHUB_REPOSITORY", "ywk8910/shorts-autopilot")
    return f"https://github.com/{repo}/releases/download/{RELEASE_TAG_PREFIX}{today}/{filename}"


def write_upload_note(path, script: dict, desc: str, dl_url: str) -> None:
    """손으로 올릴 때 붙여넣기만 하면 되도록 Release 본문에 쓸 메모를 만든다."""
    body = "\n".join([
        f"## {script['title']}", "",
        f"**영상 받기 →** {dl_url}", "",
        "### 제목", "```", script["title"], "```", "",
        "### 설명", "```", desc, "```", "",
        "### 태그", "```", " ".join(script["hashtags"]), "```", "",
        "올리는 곳: YouTube 앱 → 만들기 → 동영상 업로드, 또는 studio.youtube.com",
        "세로 영상에 60초 미만이라 Shorts로 자동 분류된다.",
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="업로드 생략")
    ap.add_argument("--silent-tts", action="store_true", help="TTS 대신 무음 (오프라인 테스트)")
    ap.add_argument("--template", default=None)
    ap.add_argument("--force", action="store_true", help="게시 기준(변동률·연속) 무시")
    args = ap.parse_args()

    cfg = C.load()
    state = load_state()
    today = today_kst()

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
        safety["min_z_to_post"] = -1
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

    script = generate(topic, cfg["llm"], cfg["safety"]["banned_title_words"], insight=insight,
                      max_sec=cfg["video"].get("duration_sec_max", 50))
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

    desc = build_description(script, topic)
    dl_url = download_url(today, out_mp4.name)
    write_upload_note(C.OUT_DIR / "upload_note.md", script, desc, dl_url)

    upload_on = cfg["channel"].get("upload_enabled", True)
    if not upload_on and not args.dry_run:
        print("[upload] config의 upload_enabled=false — 업로드를 건너뜁니다 "
              "(검수 통과 후 true로 변경)")

    video_id, uploaded = None, False
    if not args.dry_run and upload_on:
        from .upload import upload, studio_link
        try:
            video_id = upload(out_mp4, script["title"], desc,
                              cfg["channel"]["default_tags"] + [h.lstrip("#") for h in script["hashtags"]],
                              cfg["channel"])
            uploaded = True
        except Exception as e:
            send(f"[shorts] {today} 업로드 실패\n{type(e).__name__}: {e}\n"
                 f"영상은 생성됐으니 Actions의 Artifacts에서 받아 수동으로 올릴 수 있습니다.")
            raise

    state["history"].append({"date": today, "topic_id": topic["id"], "template": template,
                             "insight_kind": script.get("insight_kind", "none"),
                             "title": script["title"], "video_id": video_id, "uploaded": uploaded,
                             "change_pct": round(topic["change_pct"], 3)})
    save_state(state)
    if uploaded:
        head = "업로드 완료 (비공개)"
    elif not upload_on:
        head = "생성 완료 (업로드 보류 — 검수 대기)"
    else:
        head = "생성만 완료(dry-run)"
    msg = [f"[shorts] {today} {head}",
           f"주제: {topic['id']} ({topic['change_pct']:+.2f}%)",
           f"인사이트: {script.get('insight_kind')} / 템플릿 {template} / {len(script['lines'])}문장"]
    if video_id:
        from .upload import studio_link
        msg.append(f"검수 후 공개: {studio_link(video_id)}")
    else:
        # 손으로 올리는 동안은 알림 자체가 작업 지시서다. 받는 링크와 붙여넣을 글을 같이 보낸다.
        msg += ["", "▼ 영상 받기", dl_url,
                "", "▼ 제목", script["title"],
                "", "▼ 설명", desc]
    short = f"[오늘의 숫자] {today}\n{script['title']}\n받아서 올리기 →"
    send("\n".join(msg), short=short, link=(None if video_id else dl_url))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
