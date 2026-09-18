"""렌더링 — matplotlib 차트 + Pillow 오버레이 → ffmpeg 파이프 → 9:16 mp4.

템플릿:
  line    : 차트가 4초에 걸쳐 그려지고, 이후 자막이 문장별로 바뀜
  counter : 첫 2초 동안 숫자가 카운트업된 뒤 차트 등장
"""
import io
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont

BG = (14, 17, 23)
FG = (240, 242, 245)
ACCENT_UP = (255, 99, 99)     # 한국 관행: 상승 빨강
ACCENT_DOWN = (86, 140, 255)  # 하락 파랑
MUTED = (140, 148, 160)


def _audio_len(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def _font_path(name: str) -> str:
    if name.endswith((".ttf", ".otf", ".ttc")) and Path(name).exists():
        return name
    for f in fm.findSystemFonts():
        if name.lower().replace(" ", "") in Path(f).name.lower().replace(" ", ""):
            return f
    # 폴백: CJK 아무거나
    for f in fm.findSystemFonts():
        if "cjk" in f.lower():
            return f
    return fm.findfont(fm.FontProperties())


def _fit_font(draw, text, font_path, max_w, start=200, floor=70):
    """폭에 맞을 때까지 폰트를 줄인다. 훅 카드의 큰 글자는 길이가 매번 다르다."""
    size = start
    while size > floor:
        f = ImageFont.truetype(font_path, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 6
    return ImageFont.truetype(font_path, floor)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _chart_png(series, fraction: float, unit: str, up: bool, font_path: str, w: int, h: int) -> Image.Image:
    n = max(2, int(len(series) * fraction))
    xs = list(range(n))
    ys = [v for _, v in series[:n]]
    prop = fm.FontProperties(fname=font_path)
    color = tuple(c / 255 for c in (ACCENT_UP if up else ACCENT_DOWN))
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100, facecolor=tuple(c / 255 for c in BG))
    ax = fig.add_axes([0.06, 0.08, 0.88, 0.84])
    ax.set_facecolor(tuple(c / 255 for c in BG))
    ax.plot(xs, ys, color=color, linewidth=5)
    ax.fill_between(xs, ys, min(v for _, v in series), color=color, alpha=0.12)
    ax.scatter([xs[-1]], [ys[-1]], s=220, color=color, zorder=5)
    allv = [v for _, v in series]
    pad = (max(allv) - min(allv)) * 0.15 or 1
    ax.set_ylim(min(allv) - pad, max(allv) + pad)
    ax.set_xlim(0, len(series) - 1)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(tuple(c / 255 for c in MUTED))
    ax.tick_params(colors=tuple(c / 255 for c in MUTED), labelsize=22)
    ax.set_xticks([0, len(series) - 1])
    ax.set_xticklabels([series[0][0], series[-1][0]], fontproperties=prop, fontsize=24)
    ax.get_xticklabels()[0].set_ha("left")
    ax.get_xticklabels()[1].set_ha("right")
    for lbl in ax.get_yticklabels():
        lbl.set_fontproperties(prop)
    ax.annotate(f"{ys[-1]:,.2f}{unit}", (xs[-1], ys[-1]), xytext=(-30, 25), textcoords="offset points",
                fontproperties=prop, fontsize=34, color="white", ha="right", weight="bold")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _fit_lines(draw, text, font_path, max_w, max_lines=4, start=58, floor=38):
    """문장 전체가 max_lines 안에 들어갈 때까지 폰트를 줄인다.

    줄 수로 잘라내면 나레이션은 끝까지 읽는데 자막만 중간에 끊긴다.
    """
    size = start
    while size > floor:
        f = ImageFont.truetype(font_path, size)
        lines = _wrap(draw, text, f, max_w)
        if len(lines) <= max_lines:
            return f, lines
        size -= 4
    f = ImageFont.truetype(font_path, floor)
    return f, _wrap(draw, text, f, max_w)[:max_lines]


def _hook_card(W, H, font_path, topic, big, hook, accent, t, dur, style):
    """0~dur초 동안 화면 전체를 쓰는 훅 카드. 첫 1초에 무슨 얘기인지 보이게 한다."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_kw = ImageFont.truetype(font_path, 46)
    f_hook = ImageFont.truetype(font_path, 62)
    f_foot = ImageFont.truetype(font_path, 30)

    ease = min(1.0, t / 0.45)                      # 0.45초에 걸쳐 나타남
    ease = 1 - (1 - ease) ** 3

    # 주제명
    kw = topic["title_kw"]
    d.text(((W - d.textlength(kw, font=f_kw)) / 2, 420), kw, font=f_kw, fill=MUTED)

    # 큰 글자 (폭에 맞춰 자동 축소)
    f_big = _fit_font(d, big, font_path, W - 120, start=210, floor=78)
    bw = d.textlength(big, font=f_big)
    by = 560 + int((1 - ease) * 40)
    if style == "counter":                          # 변주: 뒤에 강조 블록
        d.rounded_rectangle([(W - bw) / 2 - 40, by - 20, (W + bw) / 2 + 40, by + f_big.size + 30],
                            24, fill=(int(accent[0] * 0.22), int(accent[1] * 0.22), int(accent[2] * 0.22)))
    d.text(((W - bw) / 2, by), big, font=f_big,
           fill=tuple(int(c * (0.35 + 0.65 * ease)) for c in accent))
    if style != "counter":
        d.rectangle([(W - bw) / 2, by + f_big.size + 34, (W + bw) / 2, by + f_big.size + 42], fill=accent)

    # 훅 문장
    if t > 0.35:
        lines = _wrap(d, hook, f_hook, W - 140)[:4]
        y = 1080
        for ln in lines:
            d.text(((W - d.textlength(ln, font=f_hook)) / 2, y), ln, font=f_hook, fill=FG)
            y += 84

    foot = f"출처: {topic['source_name']} · 기준일 {topic['series'][-1][0]} · AI 음성"
    d.text((60, H - 90), foot, font=f_foot, fill=MUTED)
    return img


def render(topic: dict, script: dict, segs: list[dict], audio: Path, out_mp4: Path,
           video_cfg: dict, template: str = "line") -> Path:
    W, H, FPS = video_cfg["width"], video_cfg["height"], video_cfg["fps"]
    font_path = _font_path(video_cfg.get("font", "NotoSansCJK-Bold"))
    f_title = ImageFont.truetype(font_path, 64)
    f_sub = ImageFont.truetype(font_path, 58)
    f_big = ImageFont.truetype(font_path, 150)
    f_foot = ImageFont.truetype(font_path, 30)
    up = topic["change_pct"] >= 0
    accent = ACCENT_UP if up else ACCENT_DOWN

    total = _audio_len(audio)
    n_frames = int(total * FPS) + FPS // 3   # 오디오보다 0.3초 길게 (마지막 자막 여유)
    chart_h = 900
    grow_sec = 4.0

    # 훅 카드: 첫 문장(=훅) 낭독이 끝날 때까지 화면 전체를 쓴다.
    # big이 없으면(인사이트 미발동) 종전처럼 바로 차트로 간다.
    big = (script.get("big") or "").strip()
    hook_txt = (script.get("hook") or (script["lines"][0] if script["lines"] else "")).strip()
    hook_sec = min(segs[0]["dur"], 6.5) if (big and segs) else 0.0
    FADE = 0.3                               # 훅 카드 -> 본 화면 크로스페이드

    # 차트 성장 프레임 캐시 (60단계)
    steps = 60
    chart_cache = [_chart_png(topic["series"], (i + 1) / steps, topic["unit"], up, font_path, W, chart_h)
                   for i in range(steps)]

    # 자막 타임라인
    timeline, t0 = [], 0.0
    for s in segs:
        timeline.append((t0, t0 + s["dur"], s["text"]))
        t0 += s["dur"]

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-i", str(audio),
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out_mp4)],
        stdin=subprocess.PIPE)

    title_lines = None
    for fi in range(n_frames):
        t = fi / FPS
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)

        # 상단 제목
        if title_lines is None:
            title_lines = _wrap(d, script["title"], f_title, W - 120)[:3]
        y = 140
        for ln in title_lines:
            d.text((60, y), ln, font=f_title, fill=FG)
            y += 78
        d.rectangle([60, y + 10, 60 + 160, y + 18], fill=accent)

        # 차트 (훅 카드가 끝난 시점부터 자라기 시작)
        frac = min(1.0, max(0.0, (t - hook_sec) / grow_sec))
        ci = min(steps - 1, int(frac * steps))
        img.paste(chart_cache[ci], (0, 520))
        d.text((60, 460), f"전일 대비 {topic['change_pct']:+.2f}%", font=f_sub, fill=accent)

        # 자막 — 전체 문장을 담고, 줄마다가 아니라 블록 하나에 배경을 깐다
        cur = next((txt for a, b, txt in timeline if a <= t < b), timeline[-1][2])
        f_cap, lines = _fit_lines(d, cur, font_path, W - 160, max_lines=4)
        lh = f_cap.size + 20
        block_h = len(lines) * lh
        y0 = 1660 - block_h                     # 블록 아래쪽을 고정 (위로 자란다)
        widest = max(d.textlength(ln, font=f_cap) for ln in lines)
        d.rounded_rectangle([(W - widest) / 2 - 28, y0 - 16,
                             (W + widest) / 2 + 28, y0 + block_h + 12], 18, fill=(0, 0, 0))
        y = y0
        for ln in lines:
            d.text(((W - d.textlength(ln, font=f_cap)) / 2, y), ln, font=f_cap, fill=FG)
            y += lh

        # 하단 출처
        foot = f"출처: {topic['source_name']} · 기준일 {topic['series'][-1][0]} · AI 음성"
        d.text((60, H - 90), foot, font=f_foot, fill=MUTED)

        # 훅 카드 구간이면 덮어쓰고, 경계에서는 부드럽게 섞는다
        if hook_sec > 0 and t < hook_sec + FADE:
            card = _hook_card(W, H, font_path, topic, big, hook_txt, accent, t, hook_sec, template)
            if t < hook_sec:
                img = card
            else:
                img = Image.blend(card, img, (t - hook_sec) / FADE)

        ff.stdin.write(img.tobytes())

    ff.stdin.close()
    ff.wait()
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg encode failed")
    return out_mp4
