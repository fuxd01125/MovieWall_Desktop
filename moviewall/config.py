import json
import sys
from pathlib import Path


def runtime_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_DIR = runtime_dir()
CONFIG_FILE = APP_DIR / "config.json"
LIBRARY_FILE = APP_DIR / "library.json"
METADATA_CACHE_FILE = APP_DIR / "metadata_cache.json"
LOCAL_METADATA_FILE = APP_DIR / "local_metadata.json"


def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_config():
    return read_json(CONFIG_FILE, {})


def load_library():
    return read_json(LIBRARY_FILE, {"items": [], "stats": {}})


def save_library(data):
    write_json(LIBRARY_FILE, data)
