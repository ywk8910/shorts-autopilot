# shorts-autopilot — "오늘의 숫자" 유튜브 숏츠 자동 생성·업로드

로컬 PC 없이 GitHub Actions만으로 매일 1편을 생성해 올리는 파이프라인입니다.
데이터 수집 → 주제 선별 → 대본(LLM, 숫자는 코드가 계산) → TTS(edge-tts) → 차트 애니메이션(matplotlib+Pillow+ffmpeg) → YouTube 업로드 → 상태 커밋 → 알림.

## 1. 로컬/아무 PC에서 1회만 할 일

```bash
pip install google-auth-oauthlib
python scripts/get_refresh_token.py client_secret.json   # 브라우저 로그인 → 값 3개 출력
```

출력된 값을 GitHub 저장소 Settings → Secrets and variables → Actions 에 등록:

```
YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN
ANTHROPIC_API_KEY   (선택, 없으면 템플릿 문장)
KAKAO_WEBHOOK_URL   (선택, 알림)
```

## 2. 오프라인 테스트 (네트워크·키 없이)

```bash
pip install -r requirements.txt          # + ffmpeg, Noto CJK 폰트
python -m shorts.main --dry-run --silent-tts --force --template counter
# out/YYYY-MM-DD_<topic>.mp4 생성 확인
```

`config.yaml`의 `sources`에 `demo`가 있으면 가짜 데이터로 돌아갑니다. 실운영 전 제거하세요.

## 3. 운영

- 스케줄: `.github/workflows/daily_short.yml` (매일 06:00 KST). Actions 탭에서 `workflow_dispatch`로 수동 실행 가능(`dry_run=true`면 영상만 Artifacts에 올라옴).
- Phase 1은 `config.yaml`의 `channel.privacy: private`로 두고 검수, Phase 2부터 `public`(지정 시각 예약 공개).
- 상태(`data/state.json`)에 업로드 이력·주제별 가중치가 쌓이며, 봇이 저장소에 커밋합니다.

## 4. 새 데이터 소스 추가

`shorts/sources/<name>.py`에 `fetch() -> list[dict]` 하나만 구현하고 `config.yaml`의 `sources`에 이름을 추가하면 됩니다. 반환 형식은 `shorts/sources/__init__.py` 상단 주석 참고.

## 5. 정책 가드 (코드로 강제)

- 변동률이 `min_change_pct_to_post` 미만이면 그날은 건너뜀 (같은 얘기 반복 방지)
- 같은 주제 `same_topic_max_streak` 초과 연속 게시 금지
- 변동률 `anomaly_change_pct` 이상이면 데이터 오류로 보고 업로드 중단 + 알림
- 제목 금지어 제거, 출처·기준일·AI 음성 표기 고정, 업로드 시 합성 미디어 자진 신고
- LLM은 코드가 계산한 사실 문장만 재구성 (숫자 생성 금지)

## 주의

- YouTube Data API 미검수 프로젝트로 올린 영상은 비공개로 고정됩니다. Compliance Audit 신청 후 통과해야 예약 공개가 동작합니다.
- 업로드 1건 = 1,600 유닛(일 10,000). 하루 1~2편이면 충분합니다.
