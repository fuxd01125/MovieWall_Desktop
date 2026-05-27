import json
import sys
import threading
from pathlib import Path


def runtime_dir():
    """User data directory: config, db, cache, generated files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def packaged_dir():
    """Bundled data directory: templates, static (read-only)."""
    if getattr(sys, "frozen", False) and hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


APP_DIR = runtime_dir()
PACKAGED_DIR = packaged_dir()
CONFIG_FILE = APP_DIR / "config.json"
METADATA_CACHE_FILE = APP_DIR / "metadata_cache.json"

# Global lock for all metadata cache operations (shared across modules)
cache_lock = threading.Lock()

# Auto-init DB on import
from moviewall.database import init_db  # noqa: E402
init_db()


def read_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        pass
    return default


def write_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


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


def get_potplayer_dpl_path():
    """Return the PotPlayer dpl (playlist) file path from config, or None.

    Priority:
      1. ``potplayer_dpl_path`` from config.json (explicit user setting)
      2. Derived from the first player's exe path (``{exe_dir}/Playlist/{exe_stem}.dpl``)
    """
    cfg = load_config()
    explicit = cfg.get("potplayer_dpl_path")
    if explicit and Path(explicit).exists():
        return str(Path(explicit).resolve())
    # Fallback: derive from player exe path
    players = load_players()
    if not players:
        return None
    exe = players[0].get("path", "")
    if not exe or not Path(exe).exists():
        return None
    exe_path = Path(exe).resolve()
    derived = exe_path.parent / "Playlist" / f"{exe_path.stem}.dpl"
    if derived.exists():
        return str(derived.resolve())
    return str(derived)


def get_potplayer_ini_path():
    """Return the PotPlayer config ini path, or None.

    Priority:
      1. ``potplayer_ini_path`` from config.json (future use)
      2. ``{exe_dir}/{exe_stem}.ini`` (portable mode)
      3. ``%%APPDATA%%/PotPlayer/{exe_stem}.ini`` (installed mode)

    Currently reserved for future progress tracking (``[RememberPlaybackPos]``).
    """
    cfg = load_config()
    explicit = cfg.get("potplayer_ini_path")
    if explicit and Path(explicit).exists():
        return str(Path(explicit).resolve())
    players = load_players()
    if not players:
        return None
    exe = players[0].get("path", "")
    if not exe or not Path(exe).exists():
        return None
    exe_path = Path(exe).resolve()
    exe_stem = exe_path.stem
    local = exe_path.parent / f"{exe_stem}.ini"
    if local.exists():
        return str(local.resolve())
    import os
    appdata = Path(os.environ.get("APPDATA", "")) / "PotPlayer" / f"{exe_stem}.ini"
    if appdata.exists():
        return str(appdata.resolve())
    return None


def normalize_categories():
    """Return dict of {folder_key: {name: display_name}}.
    Media type (movie/show) is now auto-detected by scanner based on file structure.
    Any old 'type' field in config is ignored for forward compatibility.
    """
    cfg = load_config()
    raw = cfg.get("categories", {"Movies": "电影", "TV Shows": "剧集", "Anime": "动漫"})
    out = {}
    for key, val in raw.items():
        if isinstance(val, str):
            out[key] = {"name": val}
        else:
            out[key] = {"name": val.get("name", key)}
    return out
