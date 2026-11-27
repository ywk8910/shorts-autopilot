"""시장 지표 소스 — yfinance (키 불필요). 코스피·코스닥·WTI 유가·금 시세 최근 90일.

주의: 지수·유가는 '사실 서술'만 합니다. 매수/매도 권유 문장은 script_gen의 SYSTEM 규칙으로 차단됩니다.
"""
from datetime import datetime, time, timezone

import yfinance as yf

ITEMS = [
    ("^KS11", "코스피 지수", "", "mkt_kospi", ["#코스피", "#증시", "#오늘의숫자"]),
    ("^KQ11", "코스닥 지수", "", "mkt_kosdaq", ["#코스닥", "#증시", "#오늘의숫자"]),
    ("CL=F", "WTI 유가", "달러", "mkt_wti", ["#유가", "#원자재", "#오늘의숫자"]),
    ("GC=F", "국제 금값", "달러", "mkt_gold", ["#금값", "#원자재", "#오늘의숫자"]),
]


# 각 시장의 하루 마감 시각(UTC). 지금이 그 전이고 마지막 봉이 오늘 날짜면 아직 장중이다.
# 16시(KST) 무렵에 돌면 코스피·코스닥은 이미 닫혔지만(15:30 KST = 06:30 UTC),
# 금·유가 선물은 한창 거래 중이라 마지막 봉이 '지금까지'의 값이다. 그걸 그날 종가처럼
# 쓰면 "+3.5%, 1년 중 상위 6%" 같은 말이 밤에 장이 끝난 뒤 뒤집힐 수 있다.
# 선물 마감은 17:00 ET = 22:00 UTC(겨울) / 21:00 UTC(여름). 늦은 쪽으로 잡아 둔다
# — 여름 한 시간 동안 확정된 봉을 하루 늦게 쓰는 건 틀린 숫자를 말하는 것보다 낫다.
CLOSE_UTC = {
    "^KS11": time(6, 30),
    "^KQ11": time(6, 30),
    "CL=F": time(22, 0),
    "GC=F": time(22, 0),
}


def _drop_open_bar(long: list[tuple[str, float]], ticker: str,
                   now: datetime | None = None) -> list[tuple[str, float]]:
    """마감 전인 오늘 봉을 뺀다. 휴장일이면 오늘 봉이 없으니 그대로 둔다."""
    now = now or datetime.now(timezone.utc)
    if long and long[-1][0] == now.date().isoformat() and now.time() < CLOSE_UTC[ticker]:
        return long[:-1]
    return long


def _facts(name: str, s: list[tuple[str, float]], unit: str) -> tuple[float, list[str]]:
    latest_d, latest = s[-1]
    prev = s[-2][1]
    chg = (latest - prev) / prev * 100
    vals = [v for _, v in s]
    hi, lo = max(vals), min(vals)
    m20 = sum(vals[-20:]) / min(20, len(vals))
    facts = [
        f"{latest_d} 기준 {name}은 {latest:,.2f}{unit}입니다.",   # 단위 상세는 context에서
        f"전 거래일 대비 {chg:+.2f}% 변동했습니다.",
        f"최근 90일 최고 {hi:,.2f}{unit}({s[vals.index(hi)][0]}), 최저 {lo:,.2f}{unit}({s[vals.index(lo)][0]})입니다.",
        f"최근 20거래일 평균 {m20:,.2f}{unit} 대비 {(latest - m20) / m20 * 100:+.2f}% 위치입니다.",
    ]
    return chg, facts


def fetch() -> list[dict]:
    out = []
    for ticker, name, unit, tid, tags in ITEMS:
        # long = 통계·희귀도 계산용 1년치, series = 차트에 그릴 최근 65거래일
        df = yf.Ticker(ticker).history(period="1y", interval="1d", auto_adjust=False)
        if df is None or len(df) < 10:
            continue
        long = [(d.strftime("%Y-%m-%d"), round(float(v), 2)) for d, v in df["Close"].dropna().items()]
        long = _drop_open_bar(long, ticker)
        s = long[-65:]
        chg, facts = _facts(name, s, unit)
        out.append({
            "id": tid, "title_kw": name, "unit": unit, "series": s, "long": long, "latest": s[-1][1],
            "change_pct": chg, "context": facts,
            "source_name": "Yahoo Finance", "source_url": f"https://finance.yahoo.com/quote/{ticker}",
            "chart_kind": "line",
            "hashtags": tags,
        })
    return out
