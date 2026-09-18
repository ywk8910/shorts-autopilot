"""TTS — edge-tts (무료). 문장별 mp3 + 길이(초)를 반환해 자막 타이밍에 사용."""
import asyncio
import subprocess
from pathlib import Path


def _duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


async def _synth(text: str, out: Path, voice: str, rate: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def synthesize(lines: list[str], workdir: Path, voice_cfg: dict, silent: bool = False) -> list[dict]:
    """[{text, path, dur}] — silent=True면 무음 파일 생성(오프라인 테스트용)."""
    workdir.mkdir(parents=True, exist_ok=True)
    segs = []
    for i, text in enumerate(lines):
        p = workdir / f"seg_{i:02d}.mp3"
        if silent:
            dur = max(2.0, len(text) * 0.16)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                            "-t", f"{dur:.2f}", "-q:a", "9", str(p)], check=True)
        else:
            asyncio.run(_synth(text, p, voice_cfg["name"], voice_cfg.get("rate", "+0%")))
            dur = _duration(p)
        segs.append({"text": text, "path": p, "dur": dur + 0.35})  # 문장 사이 0.35초 여백
    return segs


def concat(segs: list[dict], out: Path) -> Path:
    """세그먼트 사이에 0.35초 무음을 넣어 하나의 mp3로 합칩니다."""
    lst = out.parent / "concat.txt"
    sil = out.parent / "sil.mp3"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                    "-t", "0.35", "-q:a", "9", str(sil)], check=True)
    with open(lst, "w", encoding="utf-8") as f:
        for s in segs:
            f.write(f"file '{s['path'].resolve()}'\nfile '{sil.resolve()}'\n")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-ar", "44100", "-ac", "2", "-b:a", "128k", str(out)], check=True)
    return out
