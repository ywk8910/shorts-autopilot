"""알림 — 카카오 '나에게 보내기', 일반 웹훅, 둘 다 없으면 stdout.

우선순위:
1) KAKAO_REST_API_KEY + KAKAO_REFRESH_TOKEN 이 있으면 카카오톡으로 보낸다.
   (kakao-fortune에서 쓰는 것과 같은 값. 그대로 이 저장소 시크릿에 복사하면 된다)
2) KAKAO_WEBHOOK_URL 이 있으면 그 주소로 POST 한다.
3) 아무것도 없으면 로그에만 남는다.

카카오는 2026년부터 새로 발급한 REST API 키에 클라이언트 시크릿을 기본으로
켜 둔다. 켜져 있으면 토큰 요청에 client_secret을 같이 보내야 하므로,
KAKAO_CLIENT_SECRET 이 있으면 함께 전송한다. (꺼져 있는 앱이면 없어도 된다)

카카오 text 템플릿은 200자 제한이 있어서, 긴 본문은 보내지 않고 짧은 요약과
링크만 보낸다. 제목·설명 전문은 어차피 Release 페이지에 있다.
"""
import os
import requests

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_TEXT_LIMIT = 190          # 규격은 200자. 잘림 방지로 여유를 둔다.


def _kakao_access_token() -> str | None:
    key = os.getenv("KAKAO_REST_API_KEY")
    refresh = os.getenv("KAKAO_REFRESH_TOKEN")
    if not (key and refresh):
        return None
    data = {
        "grant_type": "refresh_token",
        "client_id": key,
        "refresh_token": refresh,
    }
    secret = os.getenv("KAKAO_CLIENT_SECRET")
    if secret:
        data["client_secret"] = secret
    r = requests.post(TOKEN_URL, data=data, timeout=10)
    r.raise_for_status()
    j = r.json()
    if j.get("refresh_token"):
        # 카카오는 리프레시 토큰 잔여기간이 1개월 미만일 때만 새 토큰을 같이 내려준다.
        # 그때 시크릿을 갈아끼우지 않으면 한두 달 뒤 알림이 조용히 끊긴다.
        # 토큰 값 자체는 로그에 남기지 않는다.
        print("::warning::카카오가 새 리프레시 토큰을 발급했습니다. "
              "저장소 시크릿 KAKAO_REFRESH_TOKEN을 갱신하지 않으면 곧 알림이 끊깁니다. "
              "scripts/get_kakao_token.py 를 다시 실행해 발급받으세요.")
    return j.get("access_token")


def _kakao_send(text: str, link: str | None) -> None:
    token = _kakao_access_token()
    if not token:
        return
    import json as _json
    obj = {"object_type": "text", "text": text[:KAKAO_TEXT_LIMIT]}
    # link는 필수 필드다. 보낼 주소가 없으면 저장소를 가리킨다.
    url = link or "https://github.com/ywk8910/shorts-autopilot/releases"
    obj["link"] = {"web_url": url, "mobile_web_url": url}
    r = requests.post(MEMO_URL,
                      headers={"Authorization": f"Bearer {token}"},
                      data={"template_object": _json.dumps(obj, ensure_ascii=False)},
                      timeout=10)
    r.raise_for_status()


def send(text: str, short: str | None = None, link: str | None = None,
         env_name: str = "KAKAO_WEBHOOK_URL") -> None:
    """text는 로그·웹훅용 전문, short는 카카오용 짧은 문구."""
    print(text)
    try:
        if os.getenv("KAKAO_REST_API_KEY") and os.getenv("KAKAO_REFRESH_TOKEN"):
            _kakao_send(short or text, link)
            return
        url = os.getenv(env_name)
        if url:
            requests.post(url, json={"text": text}, timeout=10)
    except Exception as e:
        # 알림 실패가 영상 생성을 망치면 안 된다.
        print(f"[notify] failed: {type(e).__name__}: {e}")
