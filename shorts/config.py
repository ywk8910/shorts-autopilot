"""config.yaml 로더 + 경로 상수."""
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "out"
DATA_DIR = ROOT / "data"
STATE_PATH = DATA_DIR / "state.json"
PERF_PATH = DATA_DIR / "perf.csv"


def load(path: Path | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)
