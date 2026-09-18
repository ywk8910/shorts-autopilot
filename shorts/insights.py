"""인사이트 탐지기 — 시계열에서 '계산해야 보이는 사실'을 찾아 그날의 훅을 만든다.

설계 원칙
- 모든 수치는 여기서 계산한다. LLM은 문장만 다듬는다(환각 차단).
- 서술은 '이런 일이 있었다'까지만. 예측·투자 판단 문장은 만들지 않는다.
- 탐지기는 조건이 맞을 때만 발동하고 흥미도 점수를 낸다. 가장 높은 것이 훅이 된다.
- 최근에 쓴 종류는 감점해서 매일 다른 구조가 나오도록 한다(반복 콘텐츠 판정 회피).

탐지기 추가 방법: detect_*(topic, others) -> Insight | None 을 만들고 DETECTORS에 등록.
"""
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Insight:
    kind: str
    score: float
    hook: str                       # 첫 문장 (2초 훅)
    body: list[str] = field(default_factory=list)
    title: str = ""                 # 영상 제목 (없으면 hook 사용)
    takeaway: str = ""              # 시청자가 가져갈 한 줄 (훅에 대한 답의 일반화)
    next_line: str = ""             # 다음에 볼 이유 (pick에서 자동으로 채움)
    big: str = ""                   # 첫 2초 훅 카드에 크게 띄울 한 덩어리


# ---------------------------------------------------------------- 유틸

def _d(s: str) -> date:
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def _long(topic: dict) -> list[tuple[str, float]]:
    """통계용 장기 시계열. 소스가 안 주면 표시용 시계열로 대체."""
    return topic.get("long") or topic["series"]


def _fmt(v: float, unit: str) -> str:
    u = unit or "포인트"                      # 지수는 단위가 비어 있다
    # 1000 이상이거나 소수부가 없으면 정수로. 그 외에는 소수점을 살린다.
    # (100.18을 "100달러"로 깎으면 "100달러선"과 구분이 안 된다)
    if abs(v) >= 1000 or abs(v - round(v)) < 0.005:
        return f"{v:,.0f}{u}"
    return f"{v:,.2f}{u}"


def _kdate(s: str, ref: str | None = None) -> str:
    """나레이션용 날짜. '2026-06-22' -> '6월 22일' (해가 다르면 연도 포함).

    edge-tts는 '2026-06-22'를 그대로 읽어버려서 반드시 변환해야 한다.
    """
    d = _d(s)
    if ref and _d(ref).year != d.year:
        return f"{d.year}년 {d.month}월 {d.day}일"
    return f"{d.month}월 {d.day}일"


def _batchim(word: str) -> bool:
    """마지막 글자에 받침이 있는지 (조사 선택용)."""
    c = word.strip()[-1] if word.strip() else ""
    if not ("가" <= c <= "힣"):
        return False
    return (ord(c) - 0xAC00) % 28 != 0


def _j(word: str, pair: str = "은는") -> str:
    """조사 붙이기. pair는 (받침O, 받침X) 순서: 은는 / 이가 / 을를."""
    return word + (pair[0] if _batchim(word) else pair[1])


def _changes(series: list[tuple[str, float]]) -> list[float]:
    return [(series[i][1] / series[i - 1][1] - 1) * 100 for i in range(1, len(series))]


# ---------------------------------------------------------------- 탐지기

def detect_recovery_asymmetry(topic: dict, others: list[dict]) -> Insight | None:
    """하락률과 회복률의 비대칭. 24% 내렸으면 32%가 올라야 원위치."""
    s = _long(topic)
    name, unit = topic["title_kw"], topic["unit"]
    latest = s[-1][1]
    vals = [v for _, v in s]
    hi = max(vals)
    hi_d = s[vals.index(hi)][0]
    dd = (latest / hi - 1) * 100            # 음수
    if dd > -8:                              # 낙폭이 작으면 할 얘기가 없다
        return None
    need = (hi / latest - 1) * 100           # 양수
    days = (_d(s[-1][0]) - _d(hi_d)).days
    return Insight(
        kind="recovery_asymmetry",
        score=min(95.0, abs(dd) * 2.5),
        hook=f"{abs(dd):.0f}% 빠진 {name}, 왜 {need:.0f}%가 올라야 제자리일까요?",
        body=[
            f"오늘 {_j(name)} {_fmt(latest, unit)}입니다.",
            f"최근 1년 고점은 {_kdate(hi_d, s[-1][0])}의 {_fmt(hi, unit)}, 거기서 {abs(dd):.1f}% 내려왔습니다.",
            f"그런데 그 고점을 되찾으려면 여기서 {need:.1f}%가 올라야 합니다.",
            "떨어질 때는 큰 숫자에서 빼고, 오를 때는 작아진 숫자에서 더하기 때문입니다.",
            "반토막이 나면 100%가, 20% 빠지면 25%가 있어야 제자리입니다.",
        ],
        takeaway="얼마나 빠졌는지보다 얼마나 올라야 하는지로 보는 편이 정확합니다.",
        big=f"-{abs(dd):.0f}% → +{need:.0f}%",
        title=f"{name} {abs(dd):.0f}% 하락, 되돌리려면 {need:.0f}% 필요한 이유",
    )


def detect_streak(topic: dict, others: list[dict]) -> Insight | None:
    """연속 상승/하락 일수와 그 희귀도."""
    s = _long(topic)
    name = topic["title_kw"]
    ch = _changes(s)
    if not ch:
        return None
    sign = 1 if ch[-1] > 0 else -1
    n = 0
    for c in reversed(ch):
        if (c > 0) == (sign > 0) and c != 0:
            n += 1
        else:
            break
    if n < 3:
        return None

    # 올해 같은 길이 이상의 연속이 몇 번 있었나
    year = _d(s[-1][0]).year
    runs, cur, cur_sign = [], 0, 0
    for (dt, _), c in zip(s[1:], ch):
        sg = 1 if c > 0 else -1
        if sg == cur_sign:
            cur += 1
        else:
            if cur >= n and _d(dt).year == year:
                runs.append(cur)
            cur, cur_sign = 1, sg
    if cur >= n:
        runs.append(cur)
    kth = len(runs)

    word = "상승" if sign > 0 else "하락"
    total = (s[-1][1] / s[-1 - n][1] - 1) * 100
    return Insight(
        kind="streak",
        score=min(92.0, n * 12 + (10 if kth <= 2 else 0)),
        hook=f"{_j(name, '이가')} {n}일 연속 {word}했습니다. 올해 {kth}번째입니다.",
        body=[
            f"{n}거래일 동안 누적 {total:+.1f}% 움직였습니다.",
            f"오늘 하루만 {topic['change_pct']:+.2f}%입니다.",
            f"올해 {n}일 이상 연속 {word}이 나온 건 이번이 {kth}번째입니다.",
            f"현재 수치는 {_fmt(s[-1][1], topic['unit'])}입니다.",
        ],
        takeaway=f"연속 기록이 방향을 말해주지는 않습니다. 다만 올해 {kth}번뿐인 일입니다.",
        big=f"{n}일 연속 {word}",
        title=f"{name} {n}일 연속 {word}, 올해 {kth}번째",
    )


def detect_rarity(topic: dict, others: list[dict]) -> Insight | None:
    """오늘 변동폭이 과거 대비 얼마나 드문가."""
    s = _long(topic)
    name = topic["title_kw"]
    ch = _changes(s)
    if len(ch) < 60:
        return None
    today = abs(ch[-1])
    bigger = sum(1 for c in ch[:-1] if abs(c) > today)
    pct = bigger / len(ch[:-1]) * 100        # 상위 몇 %
    if pct > 8:                               # 흔한 움직임이면 패스
        return None
    word = "상승" if topic["change_pct"] > 0 else "하락"   # 표시되는 숫자와 부호를 맞춘다
    days = len(ch)
    rank = bigger + 1                         # 오늘이 몇 번째로 큰 움직임인가

    if rank <= 5:                             # 드물면 순위로 말하는 편이 훨씬 세다
        hook = f"{name}, 1년 중 {rank}번째로 큰 하루였습니다."
        title = f"{name} {topic['change_pct']:+.1f}%, 1년 중 {rank}번째로 큰 하루"
        detail = f"최근 {days}거래일 가운데 이보다 크게 움직인 날은 {bigger}일뿐입니다."
    else:
        hook = f"{name}, 1년 중 상위 {pct:.1f}%에 드는 하루였습니다."
        title = f"{name} {topic['change_pct']:+.1f}%, 1년 중 상위 {pct:.1f}%"
        detail = f"최근 {days}거래일 중 이보다 크게 움직인 날은 {bigger}일입니다."

    return Insight(
        kind="rarity",
        score=min(94.0, 95 - pct * 4),
        hook=hook,
        body=[
            f"오늘 {_j(name)} {abs(topic['change_pct']):.2f}% {word}했습니다.",
            detail,
            f"현재 {_fmt(s[-1][1], topic['unit'])}입니다.",
        ],
        takeaway="1년에 손에 꼽는 날이었다는 뜻입니다.",
        big=(f"1년 중 {rank}번째" if rank <= 5 else f"상위 {pct:.1f}%"),
        title=title,
    )


def _round_step(v: float) -> float:
    """이정표 간격. 너무 촘촘하면 '95달러선' 같은 약한 이정표가 만들어진다."""
    if v >= 5000:
        return 500.0
    if v >= 1000:
        return 100.0
    return 10.0


def _span_word(days: int) -> str:
    if days >= 330:
        return "1년"
    if days >= 55:
        return f"{days // 30}개월"
    return f"{days}일"


def _cross(s: list[tuple[str, float]], level: float, up: bool):
    """level을 방금 통과했는지. (통과일, 통과 후 경과 거래일, 직전에 그쪽이던 마지막 날|None).

    핵심은 '언제 넘었나'가 아니라 '넘기 전에 마지막으로 그쪽이었던 게 언제인가'다.
    어제 아래 있다가 오늘 넘은 걸 "1일 만"이라고 하면 이야기가 되지 않는다.
    """
    side = (lambda v: v >= level) if up else (lambda v: v < level)
    i = len(s) - 1
    while i >= 0 and side(s[i][1]):
        i -= 1
    cross_i = i + 1
    if cross_i == 0:                      # 구간 내내 그쪽이었다 = 돌파 뉴스가 아니다
        return None
    bars = len(s) - cross_i               # 통과 후 머문 거래일 수 (1 = 오늘 통과)
    if bars > 10:
        return None
    prev = next((s[k][0] for k in range(cross_i - 1, -1, -1) if side(s[k][1])), None)
    return s[cross_i][0], bars, prev


def detect_milestone(topic: dict, others: list[dict]) -> Insight | None:
    """라운드 숫자 돌파(상향·하향) 또는 근접."""
    s = _long(topic)
    name, unit = topic["title_kw"], topic["unit"]
    latest = s[-1][1]
    step = _round_step(latest)
    up_lv = (int(latest / step) + 1) * step
    down_lv = int(latest / step) * step
    span = _span_word((_d(s[-1][0]) - _d(s[0][0])).days)

    for level, going_up in ((down_lv, True), (up_lv, False)):
        got = _cross(s, level, going_up)
        if not got:
            continue
        cross_date, bars, prev = got
        tgt = f"{level:,.0f}{unit}"
        side_n = "위" if going_up else "아래"
        sideword = "웃돌고" if going_up else "밑돌고"
        pos = abs(latest / level - 1) * 100
        if pos > 3.0:                     # 이미 한참 지나왔으면 이정표 이야기가 아니다
            continue

        when = f"{span} 만의" if prev is None else f"{(_d(cross_date) - _d(prev)).days}일 만의"
        word = "돌파" if going_up else "이탈"

        # 훅은 짧게. 2초 안에 읽혀야 한다.
        hook = f"{name}, {when} {tgt} {word}입니다."

        body = [f"오늘 {_j(name)} {_fmt(latest, unit)}, 그 선을 {pos:.2f}% {sideword} 있습니다."]
        if bars > 1:
            body.append(f"넘어선 지 {bars}거래일째입니다." if going_up
                        else f"내준 지 {bars}거래일째입니다.")
        if prev is None:
            old_d, old_v = s[0]
            body.append(f"{_kdate(old_d, s[-1][0])}에는 {_fmt(old_v, unit)}였습니다. "
                        f"그 사이 {(latest / old_v - 1) * 100:+.0f}% 움직였습니다.")
        else:
            body.append(f"직전에 {tgt} {side_n}에 있던 마지막 날은 {_kdate(prev, s[-1][0])}입니다.")
            body.append(f"그 사이가 {(_d(cross_date) - _d(prev)).days}일입니다.")

        return Insight(
            kind="milestone",
            score=84.0 if prev is None else 78.0,
            hook=hook,
            body=body,
            takeaway="0이 붙는 숫자가 가치를 바꾸지는 않지만, 사람들이 가장 많이 세는 자리입니다.",
            title=f"{name}, {when} {tgt} {word}",
            big=f"{tgt} {'돌파' if going_up else '이탈'}",
        )

    gap = (up_lv / latest - 1) * 100
    if gap > 3.0:
        return None
    tgt = f"{up_lv:,.0f}{unit}"
    above = [dt for dt, v in s if v >= up_lv]
    return Insight(
        kind="milestone",
        score=75.0 if gap <= 1.0 else 58.0,
        hook=f"{name}, {tgt}선까지 {gap:.2f}% 남았습니다.",
        body=[
            f"오늘 {_j(name)} {_fmt(latest, unit)}입니다.",
            f"{tgt}까지는 {_fmt(up_lv - latest, unit)}, {gap:.2f}% 거리입니다.",
            (f"마지막으로 그 위에 있던 날은 {_kdate(above[-1], s[-1][0])}입니다." if above
             else f"최근 {span} 동안 {tgt}를 넘은 적은 없습니다."),
        ],
        takeaway="0이 붙는 숫자가 가치를 바꾸지는 않지만, 사람들이 가장 많이 세는 자리입니다.",
        title=f"{name}, {tgt}선까지 {gap:.1f}%",
        big=f"{tgt}까지 {gap:.1f}%",
    )


PAIRS = {
    "mkt_kospi": "mkt_kosdaq",
    "mkt_kosdaq": "mkt_kospi",
    "mkt_wti": "mkt_gold",
    "mkt_gold": "mkt_wti",
}


def detect_divergence(topic: dict, others: list[dict]) -> Insight | None:
    """짝지어진 두 지표가 반대로 움직인 날과 그 빈도."""
    pid = PAIRS.get(topic["id"])
    peer = next((t for t in others if t["id"] == pid), None)
    if not peer:
        return None
    a, b = topic["change_pct"], peer["change_pct"]
    if (a > 0) == (b > 0) or min(abs(a), abs(b)) < 0.3:
        return None

    # 올해 반대로 움직인 날 세기 (날짜 기준 정렬 병합)
    ma = dict(_long(topic))
    mb = dict(_long(peer))
    year = _d(topic["series"][-1][0]).year
    common = sorted(set(ma) & set(mb))
    cnt = 0
    for i in range(1, len(common)):
        if _d(common[i]).year != year:
            continue
        ca = ma[common[i]] / ma[common[i - 1]] - 1
        cb = mb[common[i]] / mb[common[i - 1]] - 1
        if (ca > 0) != (cb > 0) and min(abs(ca), abs(cb)) >= 0.003:
            cnt += 1
    cnt = max(cnt, 1)                         # 오늘이 최소 1일

    ua, ub = ("올랐", "내렸") if a > 0 else ("내렸", "올랐")
    na, nb = topic["title_kw"], peer["title_kw"]
    return Insight(
        kind="divergence",
        score=68.0 + (12 if cnt <= 10 else 0),
        hook=f"오늘 {_j(na)} {ua}는데 {_j(nb)} {ub}습니다.",
        body=[
            f"{na} {a:+.2f}%, {nb} {b:+.2f}%입니다.",
            f"올해 두 지표가 반대로 움직인 날은 오늘 포함 {cnt}일입니다.",
            f"{_j(na)} {_fmt(topic['latest'], topic['unit'])}, "
            f"{_j(nb)} {_fmt(peer['latest'], peer['unit'])}입니다.",
        ],
        takeaway="같은 시장에서도 대형주와 중소형주에 다른 힘이 작용했다는 신호입니다.",
        big=f"{a:+.1f}% vs {b:+.1f}%",
        title=f"{_j(na)} {ua}는데 {_j(nb)} {ub}다",
    )


def _usdkrw(others: list[dict]) -> float | None:
    t = next((t for t in others if t["id"] == "fx_usdkrw"), None)
    return t["latest"] if t else None


def detect_life_translation(topic: dict, others: list[dict]) -> Insight | None:
    """환율·유가를 생활 단위로 환산. 3개월 전과 비교해 체감 차이를 만든다."""
    s = _long(topic)
    tid = topic["id"]
    if len(s) < 60:
        return None
    latest = s[-1][1]
    past_d, past = s[-61]

    if tid == "fx_usdkrw":
        now100 = latest * 100
        then100 = past * 100
        diff = now100 - then100
        word = "더" if diff > 0 else "덜"
        return Insight(
            kind="life_translation",
            score=72.0,
            hook=f"지금 환율이면 100달러 직구에 3개월 전보다 {abs(diff):,.0f}원을 {word} 내야 합니다.",
            body=[
                f"오늘 원/달러 환율은 {latest:,.0f}원입니다.",
                f"100달러짜리를 사면 {now100:,.0f}원, {_kdate(past_d, s[-1][0])}에는 {then100:,.0f}원이었습니다.",
                f"같은 물건인데 {abs(diff):,.0f}원 차이가 납니다.",
                f"3개월 새 환율이 {(latest / past - 1) * 100:+.1f}% 움직인 결과입니다.",
            ],
            takeaway="몇 퍼센트는 잘 안 와닿지만 장바구니로 바꾸면 이만큼입니다.",
            big=f"{'+' if diff > 0 else '-'}{abs(diff):,.0f}원",
            title=f"100달러 직구, 3개월 만에 {abs(diff):,.0f}원 {word} 내는 이유",
        )

    if tid == "mkt_wti":
        fx = _usdkrw(others)
        if not fx:
            return None
        lit_now = latest / 158.987 * fx      # 원유 1리터 원가(세금·정제비 제외)
        lit_then = past / 158.987 * fx
        return Insight(
            kind="life_translation",
            score=68.0,
            hook=f"지금 국제 유가를 리터로 바꾸면 원유 자체는 {lit_now:,.0f}원입니다.",
            body=[
                f"WTI는 배럴당 {latest:,.2f}달러, 1배럴은 159리터입니다.",
                f"환율 {fx:,.0f}원을 적용하면 리터당 약 {lit_now:,.0f}원입니다.",
                f"{_kdate(past_d, s[-1][0])}에는 {lit_then:,.0f}원이었습니다.",
                "주유소 가격과 다른 이유는 세금과 정제·유통 비용이 빠진 원가이기 때문입니다.",
            ],
            takeaway="주유비의 대부분은 기름값이 아니라 세금과 유통비라는 뜻입니다.",
            big=f"리터 {lit_now:,.0f}원",
            title=f"국제 유가를 리터로 바꾸면 {lit_now:,.0f}원",
        )
    return None


DETECTORS = [
    detect_recovery_asymmetry,
    detect_streak,
    detect_rarity,
    detect_milestone,
    detect_divergence,
    detect_life_translation,
]


def _watch_next(topic: dict, used_kind: str) -> str:
    """다음에 볼 이유를 데이터에서 만든다. 매번 같은 마무리 문장을 쓰지 않기 위함.

    예측이 아니라 '지켜볼 지점'만 제시한다. "오를 것"이라고 말하지 않는다.
    """
    s = _long(topic)
    name, unit = topic["title_kw"], topic["unit"]
    latest = s[-1][1]
    vals = [v for _, v in s]

    # 1순위: 가까운 라운드 숫자 (이정표 탐지기가 이미 쓴 경우는 건너뜀)
    if used_kind != "milestone":
        step = _round_step(latest)
        up = (int(latest / step) + 1) * step
        gap = (up / latest - 1) * 100
        tgt_next = f"{up:,.0f}{unit}"
        if gap <= 4.0:
            return f"{name} {tgt_next}선까지는 {gap:.1f}% 남았습니다. 닿는 날 다시 정리하겠습니다."

    # 2순위: 고점 회복까지 남은 거리 (복구 탐지기가 이미 쓴 경우는 건너뜀)
    hi = max(vals)
    need = (hi / latest - 1) * 100
    if used_kind != "recovery_asymmetry" and need > 3:
        return f"최근 1년 고점까지는 아직 {need:.0f}% 남았습니다. 좁혀지면 다시 짚어 드리겠습니다."

    # 3순위: 저점 대비 위치
    lo = min(vals)
    up_from_lo = (latest / lo - 1) * 100
    if up_from_lo > 3:
        return f"최근 1년 저점에서는 {up_from_lo:.0f}% 올라온 자리입니다. 내일 이어서 보겠습니다."

    return "내일도 숫자 하나로 정리해 드립니다."


def pick(topic: dict, others: list[dict], recent_kinds: list[str] | None = None) -> Insight | None:
    """조건이 맞는 탐지기 중 점수가 가장 높은 것. 최근에 쓴 종류는 감점."""
    recent = recent_kinds or []
    found = []
    for fn in DETECTORS:
        try:
            ins = fn(topic, others)
        except Exception as e:
            print(f"[insight] {fn.__name__} 실패: {e}")
            continue
        if not ins:
            continue
        # 최근에 자주 쓴 종류일수록 크게 감점 (한 종류가 독점하는 것을 막는다)
        ins.score -= 22 * recent[-3:].count(ins.kind) + 8 * recent[-7:].count(ins.kind)
        found.append(ins)
    if not found:
        return None

    found.sort(key=lambda i: -i.score)
    log = ", ".join(f"{i.kind}:{i.score:.0f}" for i in found)

    # 직전 영상과 같은 종류는 대안이 있으면 아예 제외한다 (연속 반복 차단)
    last = recent[-1] if recent else None
    pool = [i for i in found if i.kind != last] or found
    chosen = pool[0]
    if not chosen.next_line:
        chosen.next_line = _watch_next(topic, chosen.kind)
    print(f"[insight] {log} -> {chosen.kind}" + (f" (직전 {last} 제외)" if last and found[0].kind == last else ""))
    return chosen
