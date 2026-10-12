"""TTS — edge-tts (무료). 문장별 mp3 + 길이(초)를 반환해 자막 타이밍에 사용.

edge-tts가 내주는 mp3는 앞뒤에 0.5초 안팎의 무음이 붙어 있어, 그대로 이어붙이면
문장 사이가 1.4초씩 벌어집니다. 합성 직후 앞뒤 무음만 잘라내고(중간 호흡은 보존)
PAUSE_SEC 간격으로 이어붙입니다.
"""
import asyncio
import base64
import json
import os
import subprocess
import time
from pathlib import Path

EDGE_RETRIES = 3          # edge-tts가 403을 내는 날이 있다. 몇 번 보고 안 되면 대체 엔진
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


async def _edge(text: str, out: Path, voice: str, rate: str) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


GTTS_TEMPO = 1.15         # gTTS는 edge-tts보다 느리다. 실측 56.4초(목표 50초) → 1.15로 보정


def _gtts(text: str, out: Path) -> None:
    """대체 엔진.

    gTTS는 읽는 속도를 지정할 수 없고 edge-tts(rate +8%)보다 느려서, 그대로 쓰면
    대본 길이 계산(script_gen의 초/글자 추정)과 어긋나 영상이 60초를 넘길 수 있다.
    60초를 넘으면 Shorts로 분류되지 않으므로 합성 직후 atempo로 속도만 맞춘다.
    """
    from gtts import gTTS
    tmp = out.with_name(out.stem + "_gtts_raw.mp3")
    gTTS(text=text, lang="ko").save(str(tmp))
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp),
                    "-filter:a", f"atempo={GTTS_TEMPO}", str(out)], check=True)
    tmp.unlink(missing_ok=True)


GCLOUD_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
GCLOUD_VOICE = "ko-KR-Neural2-A"   # 여성 한국어. Neural2는 월 100만 자까지 무료(사용량 월 9천 자)
_gcloud_token: list = [None, 0.0]  # (토큰, 만료 epoch) — 한 실행 안에서 재사용


def _gcloud_access_token() -> str | None:
    """서비스 계정 JSON(시크릿 GCP_TTS_KEY)으로 액세스 토큰을 얻는다.

    google-cloud-texttospeech 패키지를 따로 깔지 않는다. 이미 유튜브 업로드용으로
    google-auth가 들어와 있고, 필요한 건 REST 한 번 호출할 토큰뿐이다.
    키가 없으면 None — 조용히 edge-tts로 넘어간다.
    """
    raw = os.getenv("GCP_TTS_KEY", "").strip()
    if not raw:
        return None
    tok, exp = _gcloud_token
    if tok and time.time() < exp - 60:
        return tok
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    creds = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/cloud-platform"])
    creds.refresh(Request())
    _gcloud_token[0] = creds.token
    _gcloud_token[1] = creds.expiry.timestamp() if creds.expiry else time.time() + 3000
    return creds.token


def _rate_to_speed(rate: str) -> float:
    """edge-tts식 "+8%"를 Cloud TTS의 speakingRate(1.08)로 바꾼다. 같은 설정을 두 번 쓰지 않도록."""
    try:
        return 1.0 + int(rate.strip().rstrip("%")) / 100.0
    except Exception:
        return 1.0


def _gcloud(text: str, out: Path, voice_cfg: dict) -> None:
    """Google Cloud Text-to-Speech. 1순위 엔진.

    edge-tts(Microsoft 비공식 엔드포인트)는 403을 내는 날이 있어 채널이 며칠씩 멈췄다.
    여기는 정식 API라 그런 일이 없고, 이 사용량에서는 요금도 0원이다.
    """
    import requests
    token = _gcloud_access_token()
    if not token:
        raise RuntimeError("GCP_TTS_KEY 없음")
    body = {
        "input": {"text": text},
        "voice": {"languageCode": "ko-KR", "name": GCLOUD_VOICE},
        "audioConfig": {"audioEncoding": "MP3",
                        "speakingRate": _rate_to_speed(voice_cfg.get("rate", "+0%"))},
    }
    r = requests.post(GCLOUD_URL, json=body, timeout=30,
                      headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    out.write_bytes(base64.b64decode(r.json()["audioContent"]))


def _speak(text: str, out: Path, voice_cfg: dict, engine: str | None) -> str:
    """한 문장을 읽어 out에 저장하고, 실제로 쓴 엔진 이름을 돌려준다.

    순서는 gcloud → edge → gtts. 앞의 것이 안 되면 다음으로 내려간다.
    edge-tts가 쓰는 Microsoft 엔드포인트는 때때로 403을 돌려준다(실측: 2026-10-12,
    GitHub Actions에서 재시도 두 번 모두 403). 서비스 쪽 사정이라 우리가 고칠 수 없고,
    그렇다고 채널을 멈출 수는 없으니 몇 번 재시도한 뒤 gTTS로 넘어간다.
    엔진은 실행마다 한 번만 정한다. 문장마다 목소리가 바뀌면 더 이상하다.
    """
    if engine == "gtts":
        _gtts(text, out)
        return "gtts"
    if engine == "gcloud":
        _gcloud(text, out, voice_cfg)
        return "gcloud"

    if engine is None and os.getenv("GCP_TTS_KEY", "").strip():
        try:
            _gcloud(text, out, voice_cfg)
            return "gcloud"
        except Exception as e:
            print(f"[tts] Cloud TTS 실패({type(e).__name__}: {str(e)[:120]}) — edge-tts로 시도합니다")

    last = None
    for attempt in range(EDGE_RETRIES):
        try:
            asyncio.run(_edge(text, out, voice_cfg["name"], voice_cfg.get("rate", "+0%")))
            return "edge"
        except Exception as e:
            last = e
            if attempt + 1 < EDGE_RETRIES:
                time.sleep(2 * (attempt + 1))
    print(f"[tts] edge-tts 실패({type(last).__name__}: {str(last)[:80]}) — gTTS로 전환합니다")
    _gtts(text, out)
    return "gtts"


def synthesize(lines: list[str], workdir: Path, voice_cfg: dict, silent: bool = False) -> list[dict]:
    """[{text, path, dur}] — silent=True면 무음 파일 생성(오프라인 테스트용)."""
    workdir.mkdir(parents=True, exist_ok=True)
    segs = []
    engine = None
    for i, text in enumerate(lines):
        raw = workdir / f"raw_{i:02d}.mp3"
        if silent:
            dur = max(2.0, len(text) * 0.16)
            p = workdir / f"seg_{i:02d}.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                            "-t", f"{dur:.2f}", "-c:a", "pcm_s16le", str(p)], check=True)
        else:
            engine = _speak(text, raw, voice_cfg, engine)
            p = _trim(raw, workdir / f"seg_{i:02d}.wav")
        segs.append({"text": text, "path": p, "dur": _duration(p) + PAUSE_SEC})
    if engine:
        print(f"[tts] engine={engine}")
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
