import json
import sys
from pathlib import Path


def runtime_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


APP_DIR = runtime_dir()
CONFIG_FILE = APP_DIR / "config.json"
METADATA_CACHE_FILE = APP_DIR / "metadata_cache.json"

# Auto-init DB on import
from moviewall.database import init_db
init_db()


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


def load_players():
    cfg = load_config()
    players = cfg.get("players")
    if players:
        return [p for p in players if Path(p.get("path", "")).exists()]
    pp = cfg.get("potplayer_path", "")
    if pp and Path(pp).exists():
        return [{"name": "PotPlayer", "path": pp}]
    return []


def normalize_categories():
    cfg = load_config()
    raw = cfg.get("categories", {"Movies": "电影", "TV Shows": "剧集", "Anime": "动漫"})
    out = {}
    for key, val in raw.items():
        if isinstance(val, str):
            out[key] = {"name": val, "type": "show" if key.lower() != "movies" else "movie"}
        else:
            out[key] = val
    return out
