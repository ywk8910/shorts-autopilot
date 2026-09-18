"""알림 — 웹훅 URL이 있으면 POST, 없으면 stdout. kakao-fortune의 카카오 봇과 같은 엔드포인트를 쓰면 됩니다."""
import os
import requests


def send(text: str, env_name: str = "KAKAO_WEBHOOK_URL") -> None:
    print(text)
    url = os.getenv(env_name)
    if not url:
        return
    try:
        requests.post(url, json={"text": text}, timeout=10)
    except Exception as e:
        print(f"[notify] failed: {e}")
