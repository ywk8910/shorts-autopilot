"""데이터 소스 플러그인 레지스트리.

각 소스 모듈은 `fetch() -> list[Topic]` 하나만 구현하면 됩니다.
Topic = dict with keys:
  id          : 고유 키 (예: "fx_usdkrw")
  title_kw    : 제목에 쓸 짧은 이름 (예: "원/달러 환율")
  unit        : 단위 문자열 (예: "원")
  series      : [(date_str, value), ...]  오래된→최신, 최소 10개
  latest      : 최신 값 (float)
  change_pct  : 전일(전기) 대비 변동률 (%)
  context     : 코드가 계산한 사실 문장 리스트 (LLM은 이 문장만 재구성)
  source_name : 출처 표기
  source_url  : 출처 URL
  chart_kind  : "line" | "bar_race" | "counter" (데이터 형태에 맞는 기본 템플릿)
"""
import importlib


def load_sources(names: list[str]):
    mods = []
    for n in names:
        mods.append(importlib.import_module(f"shorts.sources.{n}"))
    return mods


def fetch_all(names: list[str]) -> list[dict]:
    topics = []
    for m in load_sources(names):
        try:
            topics.extend(m.fetch())
        except Exception as e:  # 한 소스 실패가 전체를 막지 않도록
            print(f"[source:{m.__name__}] fetch failed: {e}")
    return topics
