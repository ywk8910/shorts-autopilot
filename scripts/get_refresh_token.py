"""refresh token 발급 (아무 PC에서 한 번만 실행).

  pip install google-auth-oauthlib google-api-python-client
  python scripts/get_refresh_token.py client_secret.json

브라우저에서 계정 → 채널을 고르게 됩니다. 채널이 여러 개면 반드시 업로드할
채널을 선택하세요. 발급 후 어떤 채널에 연결됐는지 바로 출력해 확인시켜 줍니다.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

secret = sys.argv[1] if len(sys.argv) > 1 else "client_secret.json"
flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
# access_type=offline + prompt=consent 가 있어야 refresh_token이 확실히 발급됩니다.
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

# 어느 채널에 연결됐는지 즉시 확인 (잘못 고르면 엉뚱한 채널에 업로드된다)
try:
    from googleapiclient.discovery import build
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    r = yt.channels().list(part="snippet,statistics", mine=True).execute()
    items = r.get("items", [])
    if not items:
        print("\n[경고] 이 계정에 연결된 YouTube 채널이 없습니다.")
        print("       채널을 먼저 만든 뒤 이 스크립트를 다시 실행하세요.")
    else:
        ch = items[0]
        print("\n=== 연결된 채널 ===")
        print("채널명 :", ch["snippet"]["title"])
        print("채널ID :", ch["id"])
        print("구독자 :", ch.get("statistics", {}).get("subscriberCount", "?"))
        print("주소   : https://www.youtube.com/channel/" + ch["id"])
        print("\n위 채널이 업로드하려는 채널이 맞는지 확인하세요.")
        print("아니라면 이 스크립트를 다시 실행해 다른 채널을 선택하면 됩니다.")
except Exception as e:
    print(f"\n[확인 실패] 채널 조회 중 오류: {e}")
    print("토큰 자체는 아래에 출력됩니다.")

cs = json.load(open(secret))["installed"]
print("\n=== GitHub Secrets ===")
print("YT_CLIENT_ID     =", cs["client_id"])
print("YT_CLIENT_SECRET =", cs["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
