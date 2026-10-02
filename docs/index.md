# shorts-autopilot

공개 경제 데이터(환율, 주가지수, 유가, 금 시세)에서 통계적으로 드문 변화를 찾아내 설명하는 짧은 세로 영상을 매일 한 편 만들고, 운영자 본인의 YouTube 채널 한 곳에 올리는 개인용 오픈소스 자동화 도구입니다.

운영자 외의 이용자가 없으며, 서비스로 배포하거나 판매하지 않습니다.

## YouTube API 서비스 이용 고지

본 도구는 **YouTube API 서비스(YouTube API Services)** 를 사용합니다. 자세한 내용은 [YouTube 서비스 약관](https://www.youtube.com/t/terms)과 [Google 개인정보처리방침](https://policies.google.com/privacy)을 참고하세요. 접근 권한은 [Google 보안 설정 페이지](https://myaccount.google.com/permissions)에서 언제든 철회할 수 있습니다.

사용하는 엔드포인트는 `youtube.videos.insert`(하루 최대 1회)와 `youtube.channels.list`(최초 설정 시 1회) 두 가지뿐입니다.

## 문서

- [개인정보처리방침 (Privacy Policy)](privacy.html)
- [서비스 약관 (Terms of Service)](terms.html)

## 동작 방식

매일 공개 데이터를 수집해, 각 지표의 일간 변동 표준편차 대비 그날의 움직임이 얼마나 드문지(z값)로 주제를 고릅니다. 고른 주제에 대해 복구 비대칭, 연속 기록, 희귀도, 이정표 돌파, 지표 간 디커플링 등의 탐지기를 돌려 그날 가장 설명할 만한 사실 하나를 찾고, 차트와 자막과 합성 음성으로 영상을 만듭니다. 모든 화면에 데이터 출처와 기준일을 표기합니다.

소스 코드: [github.com/ywk8910/shorts-autopilot](https://github.com/ywk8910/shorts-autopilot)

문의: ywk891010@gmail.com
