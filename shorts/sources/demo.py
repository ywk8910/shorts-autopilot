"""오프라인 테스트용 가짜 소스 — config.yaml sources에 'demo'를 넣으면 네트워크 없이 파이프라인을 끝까지 돌릴 수 있습니다."""
import math
import random
from datetime import date, timedelta


def fetch() -> list[dict]:
    random.seed(7)
    long, v = [], 1380.0
    for i in range(250):
        d = date.today() - timedelta(days=250 - i)
        v = v * (1 + random.uniform(-0.006, 0.006)) + math.sin(i / 6) * 1.5
        long.append((d.isoformat(), round(v, 2)))
    s = long[-60:]
    latest, prev = s[-1][1], s[-2][1]
    chg = (latest - prev) / prev * 100
    return [{
        "id": "demo_usdkrw",
        "title_kw": "원/달러 환율(데모)",
        "unit": "원",
        "series": s,
        "long": long,
        "latest": latest,
        "change_pct": chg,
        "context": [
            f"{s[-1][0]} 기준 원/달러 환율은 {latest:,.2f}원입니다.",
            f"전 영업일 대비 {chg:+.2f}% 변동했습니다.",
            f"최근 60일 최고는 {max(v for _, v in s):,.2f}원, 최저는 {min(v for _, v in s):,.2f}원입니다.",
            "최근 20영업일 평균과 비교하면 평균 부근에 머물러 있습니다.",
        ],
        "source_name": "데모 데이터",
        "source_url": "https://example.com",
        "chart_kind": "line",
        "hashtags": ["#환율", "#경제", "#오늘의숫자"],
    }]
