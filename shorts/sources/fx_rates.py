"""환율 소스 — Frankfurter API (ECB 기준, 키 불필요).

USD/KRW, JPY(100엔)/KRW, EUR/KRW 최근 60영업일 시계열을 주제 후보로 반환합니다.
"""
from datetime import date, timedelta
import requests

BASE = "https://api.frankfurter.app"
PAIRS = [
    ("USD", 1, "원/달러 환율", "fx_usdkrw"),
    ("JPY", 100, "원/100엔 환율", "fx_jpykrw"),
    ("EUR", 1, "원/유로 환율", "fx_eurkrw"),
]


def _series(base: str, mult: int, days: int = 90) -> list[tuple[str, float]]:
    start = (date.today() - timedelta(days=days)).isoformat()
    r = requests.get(f"{BASE}/{start}..", params={"from": base, "to": "KRW"}, timeout=20)
    r.raise_for_status()
    rates = r.json()["rates"]
    return [(d, round(v["KRW"] * mult, 2)) for d, v in sorted(rates.items())]


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
        f"{latest_d} 기준 {name}은 {latest:,.2f}{unit}입니다.",
        f"전 영업일 대비 {chg:+.2f}% ({latest - prev:+,.2f}{unit}) 변동했습니다.",
        f"최근 90일 최고는 {hi_d}의 {hi:,.2f}{unit}, 최저는 {lo_d}의 {lo:,.2f}{unit}입니다.",
        f"최근 20영업일 평균은 {m20:,.2f}{unit}이며, 현재는 평균 대비 {(latest - m20) / m20 * 100:+.2f}%입니다.",
    ]
    return chg, facts


def fetch() -> list[dict]:
    out = []
    for base, mult, name, tid in PAIRS:
        s = _series(base, mult)
        if len(s) < 10:
            continue
        chg, facts = _facts(name, s, "원")
        out.append({
            "id": tid,
            "title_kw": name,
            "unit": "원",
            "series": s,
            "latest": s[-1][1],
            "change_pct": chg,
            "context": facts,
            "source_name": "Frankfurter (ECB 고시 환율)",
            "source_url": "https://www.frankfurter.app",
            "chart_kind": "line",
        })
    return out
