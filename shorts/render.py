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
    intro_sec = 2.0 if template == "counter" else 0.0

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

        # 카운터 인트로
        if t < intro_sec:
            frac = min(1.0, t / intro_sec)
            val = topic["latest"] * (0.6 + 0.4 * frac)
            txt = f"{val:,.2f}"
            tw = d.textlength(txt, font=f_big)
            d.text(((W - tw) / 2, 760), txt, font=f_big, fill=accent)
            d.text(((W - d.textlength(topic["title_kw"], font=f_sub)) / 2, 940),
                   topic["title_kw"], font=f_sub, fill=MUTED)
        else:
            frac = min(1.0, (t - intro_sec) / grow_sec)
            ci = min(steps - 1, int(frac * steps))
            img.paste(chart_cache[ci], (0, 520))
            chg = f"{topic['change_pct']:+.2f}%"
            d.text((60, 460), f"전일 대비 {chg}", font=f_sub, fill=accent)

        # 자막
        cur = next((txt for a, b, txt in timeline if a <= t < b), timeline[-1][2])
        lines = _wrap(d, cur, f_sub, W - 140)[:3]
        y = 1560 - (len(lines) - 1) * 70
        for ln in lines:
            tw = d.textlength(ln, font=f_sub)
            d.rounded_rectangle([(W - tw) / 2 - 24, y - 8, (W + tw) / 2 + 24, y + 70], 16, fill=(0, 0, 0))
            d.text(((W - tw) / 2, y), ln, font=f_sub, fill=FG)
            y += 78

        # 하단 출처
        foot = f"출처: {topic['source_name']} · 기준일 {topic['series'][-1][0]} · AI 음성"
        d.text((60, H - 90), foot, font=f_foot, fill=MUTED)

        ff.stdin.write(img.tobytes())

    ff.stdin.close()
    ff.wait()
    if ff.returncode != 0:
        raise RuntimeError("ffmpeg encode failed")
    return out_mp4
