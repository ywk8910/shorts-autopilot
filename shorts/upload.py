"""YouTube Data API 업로드 — refresh token 기반 (브라우저 불필요).

검수(Compliance Audit) 전에는 API로 올린 영상이 강제로 비공개 고정입니다.
config의 privacy가 public이어도 실제로는 공개되지 않으니, 검수 통과 후에 전환하세요.
"""
import os
import random
import socket
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httplib2
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
KST = timezone(timedelta(hours=9))

RETRIABLE_STATUS = (500, 502, 503, 504)
RETRIABLE_EXC = (httplib2.HttpLib2Error, IOError, socket.timeout, ConnectionError)
MAX_RETRIES = 6


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


def _status(channel_cfg: dict) -> dict:
    """privacy 설정에 따른 status 블록.

    public이면 '비공개 + publishAt(예약)'으로 올린다. publishAt은 privacyStatus가
    private일 때만 허용되기 때문이다.
    """
    st = {
        "privacyStatus": "private",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,      # AI 합성 음성 자진 신고
    }
    if channel_cfg.get("privacy") != "public":
        return st
    hour = int(channel_cfg.get("publish_hour_kst", 7))
    now = datetime.now(KST)
    at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if at <= now + timedelta(minutes=10):     # 너무 임박하면 다음 날로
        at += timedelta(days=1)
    st["publishAt"] = at.astimezone(timezone.utc).isoformat()
    return st


def upload(video: Path, title: str, description: str, tags: list[str], channel_cfg: dict) -> str:
    yt = _client()
    body = {
        "snippet": {"title": title[:100], "description": description[:4900], "tags": tags[:30],
                    "categoryId": channel_cfg.get("category_id", "28"),
                    "defaultLanguage": "ko", "defaultAudioLanguage": "ko"},
        "status": _status(channel_cfg),
    }
    media = MediaFileUpload(str(video), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    resp, attempt = None, 0
    while resp is None:
        try:
            _, resp = req.next_chunk()
        except HttpError as e:
            if e.resp.status not in RETRIABLE_STATUS:
                raise                          # 400/403 등은 재시도해도 소용없다
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            wait = min(60, 2 ** attempt) + random.random()
            print(f"[upload] {e.resp.status} 재시도 {attempt}/{MAX_RETRIES} — {wait:.1f}초 후")
            time.sleep(wait)
        except RETRIABLE_EXC as e:
            attempt += 1
            if attempt > MAX_RETRIES:
                raise
            wait = min(60, 2 ** attempt) + random.random()
            print(f"[upload] 네트워크 오류({e}) 재시도 {attempt}/{MAX_RETRIES} — {wait:.1f}초 후")
            time.sleep(wait)

    vid = resp["id"]
    print(f"[upload] 완료 {vid} (privacyStatus={resp.get('status', {}).get('privacyStatus')})")
    return vid


def studio_link(video_id: str) -> str:
    """검수 전에는 공개 URL이 열리지 않으므로 Studio 편집 링크를 준다."""
    return f"https://studio.youtube.com/video/{video_id}/edit"
