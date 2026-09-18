"""TTS — edge-tts (무료). 문장별 mp3 + 길이(초)를 반환해 자막 타이밍에 사용.

edge-tts가 내주는 mp3는 앞뒤에 0.5초 안팎의 무음이 붙어 있어, 그대로 이어붙이면
문장 사이가 1.4초씩 벌어집니다. 합성 직후 앞뒤 무음만 잘라내고(중간 호흡은 보존)
PAUSE_SEC 간격으로 이어붙입니다.
"""
import asyncio
import subprocess
from pathlib import Path

PAUSE_SEC = 0.25          # 문장 사이 간격
TRIM_THRESHOLD = "-50dB"  # 이보다 조용하면 무음으로 간주

# 앞쪽 무음 제거 → 뒤집어서 같은 작업 → 다시 뒤집기 = 앞뒤만 제거, 중간은 보존
_TRIM_AF = (
    f"silenceremove=start_periods=1:start_threshold={TRIM_THRESHOLD}:start_silence=0.06,"
    "areverse,"
    f"silenceremove=start_periods=1:start_threshold={TRIM_THRESHOLD}:start_silence=0.06,"
    "areverse"
)


def _duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def _to_wav(src: Path, dst: Path, af: str | None = None) -> Path:
    """WAV로 디코딩. mp3는 인코더 패딩이 붙어 길이가 미세하게 어긋나므로
    중간 파일은 전부 WAV로 다룬다(자막-음성 싱크가 뒤로 갈수록 밀리는 원인)."""
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src)]
    if af:
        cmd += ["-af", af]
    cmd += ["-ar", "44100", "-ac", "1", "-c:a", "pcm_s16le", str(dst)]
    subprocess.run(cmd, check=True)
    return dst


def _trim(src: Path, dst: Path) -> Path:
    """앞뒤 무음 제거 후 WAV로. 결과가 비었으면 자르지 않은 WAV를 쓴다."""
    try:
        _to_wav(src, dst, _TRIM_AF)
        if _duration(dst) >= 0.3:
            return dst
    except Exception as e:
        print(f"[tts] trim skipped ({e})")
    return _to_wav(src, dst.with_name(dst.stem + "_raw.wav"))


async def _synth(text: str, out: Path, voice: str, rate: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def synthesize(lines: list[str], workdir: Path, voice_cfg: dict, silent: bool = False) -> list[dict]:
    """[{text, path, dur}] — silent=True면 무음 파일 생성(오프라인 테스트용)."""
    workdir.mkdir(parents=True, exist_ok=True)
    segs = []
    for i, text in enumerate(lines):
        raw = workdir / f"raw_{i:02d}.mp3"
        if silent:
            dur = max(2.0, len(text) * 0.16)
            p = workdir / f"seg_{i:02d}.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                            "-t", f"{dur:.2f}", "-c:a", "pcm_s16le", str(p)], check=True)
        else:
            asyncio.run(_synth(text, raw, voice_cfg["name"], voice_cfg.get("rate", "+0%")))
            p = _trim(raw, workdir / f"seg_{i:02d}.wav")
        segs.append({"text": text, "path": p, "dur": _duration(p) + PAUSE_SEC})
    total = sum(s["dur"] for s in segs)
    print(f"[tts] {len(segs)} segments, {total:.1f}s (pause {PAUSE_SEC}s)")
    return segs


def concat(segs: list[dict], out: Path) -> Path:
    """세그먼트 사이에 PAUSE_SEC 무음을 넣어 하나로 합친다.

    concat 디먹서로 mp3를 이어붙이면 파일마다 인코더 패딩(20~30ms)이 쌓여
    뒤로 갈수록 자막과 음성이 어긋난다. 전부 디코딩해서 apad로 정확히 붙인다.
    """
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for seg in segs:
        cmd += ["-i", str(seg["path"])]
    n = len(segs)
    chains = "".join(f"[{i}:a]aresample=44100,apad=pad_dur={PAUSE_SEC}[p{i}];" for i in range(n))
    joins = "".join(f"[p{i}]" for i in range(n))
    cmd += ["-filter_complex", f"{chains}{joins}concat=n={n}:v=0:a=1[out]",
            "-map", "[out]", "-ac", "2", "-b:a", "128k", str(out)]
    subprocess.run(cmd, check=True)
    print(f"[tts] concat -> {_duration(out):.2f}s (예상 {sum(s['dur'] for s in segs):.2f}s)")
    return out
