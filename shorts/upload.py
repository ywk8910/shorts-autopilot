"""YouTube Data API 업로드 — refresh token 기반 (브라우저 불필요)."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
KST = timezone(timedelta(hours=9))


def _client():
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(video: Path, title: str, description: str, tags: list[str], channel_cfg: dict) -> str:
    yt = _client()
    privacy = channel_cfg.get("privacy", "private")
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
              # 합성 음성 사용 자진 신고 (변경된 콘텐츠 공개)
              "containsSyntheticMedia": True}
    # public이면 지정 시각(KST)에 예약 공개
    if privacy == "public":
        hour = int(channel_cfg.get("publish_hour_kst", 7))
        now = datetime.now(KST)
        at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if at <= now:
            at += timedelta(days=1)
        status = {**status, "privacyStatus": "private", "publishAt": at.astimezone(timezone.utc).isoformat()}
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:30],
                    "categoryId": channel_cfg.get("category_id", "28"),
                    "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
        "status": status,
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]
