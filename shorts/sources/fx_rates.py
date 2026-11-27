"""환율 소스 — Yahoo Finance, 매일 15:30(KST) 시점 값. 키 불필요.

USD/KRW, JPY(100엔)/KRW, EUR/KRW를 주제 후보로 반환합니다.

왜 15:30인가:
서울 외환시장 주간 거래가 15:30에 끝나고, 국내에서 말하는 '오늘 환율 종가'가 이 시각
값이다. 예전 소스(Frankfurter/ECB)는 기준율을 한국 시간 자정에 발표해서, 16시에 돌려도
늘 전날 값이었다(실측: 11/27 17:24에 최신이 11/26). 그래서 영상 열에 셋은 하루 묵은
환율이었다.

어떻게 뽑나:
30분봉 중 15:00에 시작하는 봉의 종가 = 15:30 시점 값. 매일 같은 시각을 쓰므로
'전일 대비'도 15:30 대 15:30으로 정확하다. Yahoo는 30분봉을 최근 60일까지만 주므로,
1년 통계(희귀도, 1년 고점, 3개월 전 비교)에 필요한 그 이전 구간은 일봉으로 이어 붙인다.
일봉은 다른 시각에 끊긴 값이지만, 하루 변동의 크기 분포를 보는 용도로는 차이가 작다.

Yahoo 환율은 역외 포함 국제 시세라 서울 외환시장 공식 종가와 소수점 단위로 다를 수 있다.
그래서 출처는 '서울 종가'가 아니라 'Yahoo Finance, 15:30 KST 기준'으로 밝힌다.
"""
from datetime import datetime, time, timedelta, timezone

import yfinance as yf

KST = timezone(timedelta(hours=9))
SNAP_BAR = time(15, 0)          # 15:00에 시작해 15:30에 끝나는 30분봉
SNAP_DONE = time(15, 30)        # 이 시각 전이면 오늘 봉이 아직 진행 중

PAIRS = [
    ("KRW=X", 1, "원/달러 환율", "fx_usdkrw"),
    ("JPYKRW=X", 100, "원/100엔 환율", "fx_jpykrw"),
    ("EURKRW=X", 1, "원/유로 환율", "fx_eurkrw"),
]


def _snapshots(df, mult: int, now: datetime | None = None) -> list[tuple[str, float]]:
    """30분봉 DataFrame에서 평일 15:30 시점 값만 골라 (날짜, 값) 목록으로."""
    now = (now or datetime.now(timezone.utc)).astimezone(KST)
    k = df["Close"].dropna()
    k.index = k.index.tz_convert(KST)
    out = []
    for ts, v in k.items():
        if ts.weekday() >= 5 or ts.time() != SNAP_BAR:
            continue
        if ts.date() == now.date() and now.time() < SNAP_DONE:
            continue                    # 15:30 전에 돌면 오늘 봉은 아직 장중이다
        out.append((ts.strftime("%Y-%m-%d"), round(float(v) * mult, 2)))
    return out


def _daily(df, mult: int) -> list[tuple[str, float]]:
    return [(d.strftime("%Y-%m-%d"), round(float(v) * mult, 2)) for d, v in df["Close"].dropna().items()]


def _series(ticker: str, mult: int) -> list[tuple[str, float]]:
    t = yf.Ticker(ticker)
    snap = _snapshots(t.history(period="59d", interval="30m", auto_adjust=False), mult)
    daily = _daily(t.history(period="1y", interval="1d", auto_adjust=False), mult)
    if not snap:                        # 30분봉을 못 받으면 일봉으로라도 (날짜 표기는 그대로 정확)
        return daily
    first = snap[0][0]
    return [(d, v) for d, v in daily if d < first] + snap


def _facts(name: str, s: list[tuple[str, float]], unit: str) -> tuple[float, list[str]]:
    latest_d, latest = s[-1]
    prev = s[-2][1]
    chg = (latest - prev) / prev * 100
    vals = [v for _, v in s]
    hi, lo = max(vals), min(vals)
    hi_d = s[vals.index(hi)][0]
    lo_d = s[vals.index(lo)][0]
    m20 = sum(vals[-20:]) / min(20, len(vals))
    facts = [
        f"{latest_d} 15:30 기준 {name}은 {latest:,.2f}{unit}입니다.",
        f"전 영업일 15:30 대비 {chg:+.2f}% ({latest - prev:+,.2f}{unit}) 변동했습니다.",
        f"최근 90일 최고는 {hi_d}의 {hi:,.2f}{unit}, 최저는 {lo_d}의 {lo:,.2f}{unit}입니다.",
        f"최근 20영업일 평균은 {m20:,.2f}{unit}이며, 현재는 평균 대비 {(latest - m20) / m20 * 100:+.2f}%입니다.",
    ]
    return chg, facts


def fetch() -> list[dict]:
    out = []
    for ticker, mult, name, tid in PAIRS:
        long = _series(ticker, mult)
        if len(long) < 10:
            continue
        s = long[-65:]                       # 차트에 그릴 구간
        chg, facts = _facts(name, s, "원")
        out.append({
            "id": tid,
            "title_kw": name,
            "unit": "원",
            "series": s,
            "long": long,                    # 통계·희귀도 계산용
            "latest": s[-1][1],
            "change_pct": chg,
            "context": facts,
            "source_name": "Yahoo Finance (15:30 KST 기준)",
            "source_url": f"https://finance.yahoo.com/quote/{ticker}",
            "chart_kind": "line",
            "hashtags": ["#환율", "#경제", "#오늘의숫자"],
        })
    return out
