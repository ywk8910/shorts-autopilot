# 개인정보처리방침 (Privacy Policy)

최종 수정일: 2026-10-02

shorts-autopilot(이하 "본 도구")은 운영자 개인이 자신의 YouTube 채널 하나를 운영하기 위해 사용하는 비상업적 자동화 스크립트입니다. 외부 사용자가 없으며, 서비스로 배포하거나 판매하지 않습니다.

## YouTube API 서비스 이용 고지

본 도구는 **YouTube API 서비스(YouTube API Services)** 를 사용합니다. 본 도구를 사용함으로써 운영자는 다음에 동의합니다.

- [YouTube 서비스 약관 (YouTube Terms of Service)](https://www.youtube.com/t/terms)
- [Google 개인정보처리방침 (Google Privacy Policy)](https://policies.google.com/privacy)

## 수집하는 정보

본 도구는 제3자의 개인정보를 수집·저장·공유하지 않습니다. 수집 대상은 다음으로 한정됩니다.

- 운영자 본인 채널의 OAuth 2.0 자격증명(refresh token). GitHub Actions의 암호화된 Secrets에만 보관되며 로그나 저장소에 기록되지 않습니다.
- 운영자 본인 채널의 영상 ID와 공개 집계 지표(조회수 등).
- 공개 경제 데이터(환율, 주가지수, 유가, 금 시세). 개인정보가 아닙니다.

본 도구는 다른 이용자의 YouTube 데이터를 조회·저장·표시하지 않으며, YouTube 콘텐츠를 스크래핑·복제·재호스팅하지 않습니다.

## 사용하는 권한 범위

| 범위 | 용도 |
| --- | --- |
| `youtube.upload` | 운영자 본인 채널에 영상 업로드 |
| `youtube.readonly` | 업로드한 본인 영상의 상태 조회 |
| `yt-analytics.readonly` | 본인 채널의 조회수·시청 지표 조회 |

## 정보의 이용

조회한 지표는 다음 영상의 주제를 고르는 데에만 사용되며, 운영자 본인의 저장소에만 보관됩니다. 외부로 전송하거나 제3자와 공유하지 않고, 광고 목적으로 사용하지 않으며, 판매하지 않습니다.

## 보관 및 삭제 정책 (Data Retention and Deletion)

- YouTube API로 가져온 데이터는 **30일을 넘겨 보관하지 않습니다.** 30일이 지난 데이터는 다음 실행 시 갱신되거나 삭제됩니다.
- 운영자가 접근 권한을 철회하면 저장된 자격증명과 파생 데이터는 **즉시 삭제**됩니다.
- 삭제를 요청하려면 아래 문의 주소로 연락하면 되며, 본 도구의 저장 데이터 전체는 GitHub 저장소의 `data/` 디렉터리를 비우는 것으로 완전히 삭제됩니다.

## 접근 권한 철회

운영자는 언제든 [Google 보안 설정 페이지](https://myaccount.google.com/permissions)에서 본 도구의 접근 권한을 철회할 수 있습니다. 철회 즉시 본 도구는 YouTube API에 접근할 수 없게 됩니다.

## 문의

ywk891010@gmail.com
