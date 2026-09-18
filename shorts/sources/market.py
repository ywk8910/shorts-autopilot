"""시장 지표 소스 — yfinance (키 불필요). 코스피·코스닥·WTI 유가·금 시세 최근 90일.

주의: 지수·유가는 '사실 서술'만 합니다. 매수/매도 권유 문장은 script_gen의 SYSTEM 규칙으로 차단됩니다.
"""
import yfinance as yf

ITEMS = [
    ("^KS11", "코스피 지수", "", "mkt_kospi"),
    ("^KQ11", "코스닥 지수", "", "mkt_kosdaq"),
    ("CL=F", "WTI 유가(달러/배럴)", "달러", "mkt_wti"),
    ("GC=F", "국제 금값(달러/온스)", "달러", "mkt_gold"),
]


def _facts(name: str, s: list[tuple[str, float]], unit: str) -> tuple[float, list[str]]:
    latest_d, latest = s[-1]
    prev = s[-2][1]
    chg = (latest - prev) / prev * 100
    vals = [v for _, v in s]
    hi, lo = max(vals), min(vals)
    m20 = sum(vals[-20:]) / min(20, len(vals))
    facts = [
        f"{latest_d} 기준 {name}은 {latest:,.2f}{unit}입니다.",
        f"전 거래일 대비 {chg:+.2f}% 변동했습니다.",
        f"최근 90일 최고 {hi:,.2f}{unit}({s[vals.index(hi)][0]}), 최저 {lo:,.2f}{unit}({s[vals.index(lo)][0]})입니다.",
        f"최근 20거래일 평균 {m20:,.2f}{unit} 대비 {(latest - m20) / m20 * 100:+.2f}% 위치입니다.",
    ]
    return chg, facts


def fetch() -> list[dict]:
    out = []
    for ticker, name, unit, tid in ITEMS:
        df = yf.Ticker(ticker).history(period="4mo", interval="1d", auto_adjust=False)
        if df is None or len(df) < 10:
            continue
        s = [(d.strftime("%Y-%m-%d"), round(float(v), 2)) for d, v in df["Close"].dropna().items()][-65:]
        chg, facts = _facts(name, s, unit)
        out.append({
            "id": tid, "title_kw": name, "unit": unit, "series": s, "latest": s[-1][1],
            "change_pct": chg, "context": facts,
            "source_name": "Yahoo Finance", "source_url": f"https://finance.yahoo.com/quote/{ticker}",
            "chart_kind": "line",
        })
    return out
