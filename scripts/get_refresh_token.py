"""refresh token 1회 발급 (아무 PC에서 한 번만 실행).

  pip install google-auth-oauthlib
  python scripts/get_refresh_token.py client_secret.json

출력된 refresh_token / client_id / client_secret 을 GitHub Secrets에 넣으면 됩니다.
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
cs = json.load(open(secret))["installed"]
print("\n=== GitHub Secrets ===")
print("YT_CLIENT_ID     =", cs["client_id"])
print("YT_CLIENT_SECRET =", cs["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
