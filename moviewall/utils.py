import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from moviewall.config import load_config, cache_lock
from moviewall.constants import VIDEO_EXTS, ART_EXTS, TMDB_IMG_BASE


def stable_id(*parts):
    raw = "||".join(str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


def hidden_subprocess_kwargs():
    if os.name != "nt":
        return {}
    kwargs = {}
    try:
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    except Exception:
        pass
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def safe_stem(text: str):
    raw = str(text or "")
    p = Path(raw)
    known_exts = set(VIDEO_EXTS) | set(ART_EXTS) | {".nfo", ".srt", ".ass", ".ssa"}
    if p.suffix.lower() in known_exts:
        return p.stem
    return p.name or raw


def normalize_key(text: str):
    text = safe_stem(text).lower()
    text = re.sub(r"\(\s*(19|20)\d{2}\s*\)", " ", text)
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_title(text: str):
    title = safe_stem(text)
    title = re.sub(r"\(\s*(19|20)\d{2}\s*\)", " ", title)
    title = re.sub(r"(?:^|[\s.\-_])\[([^\[\]]+)\]", " ", title)
    title = re.sub(r"\b(1080p|2160p|720p|480p|4K|BluRay|WEB-DL|WEBRip|HDRip|DVDRip|BDRip|HDR|HEVC|x265|x264|AAC|DDP5\.1|H\.264|H\.265)\b", " ", title, flags=re.I)
    title = re.sub(r"\b[Ss]\d{1,2}[Ee]\d{1,3}\b", " ", title)
    title = re.sub(r"(?<!\d)[_\-]+(?!\d)", " ", title)
    title = re.sub(r"\.(?!\s*\d)", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title or safe_stem(text)


def parse_year(text: str):
    m = re.search(r"\((19|20)\d{2}\)", str(text))
    return m.group(0).strip("()") if m else ""


_CN_NUM_SEASON = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}

def parse_season_number(text: str):
    s = str(text)
    m = re.search(r"Season\s*(\d+)", s, flags=re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*(\d+)\s*季", s)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*([一二三四五六七八九十]+)\s*季", s)
    if m:
        return _CN_NUM_SEASON.get(m.group(1), 1)
    m = re.search(r"[Ss](\d{1,2})", s)
    if m:
        return int(m.group(1))
    return 1


_CN_NUM = {"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9,"十":10}

def parse_episode_number(text: str):
    s = str(text)
    m = re.search(r"[Ss]\d{1,2}[Ee](\d{1,3})", s)
    if m:
        return int(m.group(1))
    m = re.search(r"[Ee][pP]?(\d{1,3})", s)
    if m:
        return int(m.group(1))
    m = re.search(r"[Tt]ape[.\s]*(\d{1,3})", s)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*(\d{1,3})\s*[话集章回]", s)
    if m:
        return int(m.group(1))
    m = re.search(r"\b[Pp](?:art)?\s*(\d{1,3})\b", s)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*([一二三四五六七八九十]+)\s*[话集章回]", s)
    if m:
        return _CN_NUM.get(m.group(1), 0)
    m = re.search(r"\b(\d{1,3})\s*[话集章回]", s)
    if m:
        return int(m.group(1))
    m = re.search(r"(?:^|[\s._\-])#\s*(\d{1,3})(?:[\s._\-]|$)", s)
    if m:
        return int(m.group(1))
    return 0


def pretty_season(n):
    return f"第 {n:02d} 季"


def pretty_episode(n):
    return f"第 {n:02d} 集" if n else "剧集"


def ffmpeg_exe():
    path = load_config().get("ffmpeg_path", "ffmpeg") or "ffmpeg"
    explicit = Path(path)
    if explicit.exists():
        return str(explicit)
    return shutil.which(path)


def generate_video_image(video_path: Path, target: Path, second=60):
    if not load_config().get("generate_thumbnails", True):
        return None
    exe = ffmpeg_exe()
    if not exe:
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 1000:
        return str(target.resolve())
    commands = [
        [exe, "-y", "-ss", str(second), "-i", str(video_path), "-frames:v", "1", "-vf", "scale=720:-1", "-q:v", "3", str(target)],
        [exe, "-y", "-ss", "15", "-i", str(video_path), "-frames:v", "1", "-vf", "scale=720:-1", "-q:v", "3", str(target)],
    ]
    for cmd in commands:
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25, **hidden_subprocess_kwargs())
            if target.exists() and target.stat().st_size > 1000:
                return str(target.resolve())
        except Exception:
            pass
    return None


def tmdb_image(path, size="w500"):
    return f"{TMDB_IMG_BASE}/{size}{path}" if path else ""


def tmdb_request(endpoint, params, _retries=2):
    cfg = load_config()
    key = (cfg.get("tmdb_api_key") or "").strip()
    if not key:
        return None
    params = dict(params or {})
    params["api_key"] = key

    from moviewall.config import read_json, write_json, METADATA_CACHE_FILE as _mcf
    # Include all query params (except api_key) in cache key so different
    # searches don't clobber each other's cached results
    _cache_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "api_key")
    ck = f"tmdb:{endpoint}:{_cache_params}"
    try:
        with cache_lock:
            cache = read_json(_mcf, {})
            cached = cache.get(ck)
            ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
            if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
                return cached["data"]
    except Exception:
        cache = {}

    url = f"https://api.themoviedb.org/3/{endpoint}?{urllib.parse.urlencode(params)}"
    for attempt in range(_retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "MovieWall/12"}), timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8")) if resp.status == 200 else None
                if data:
                    try:
                        with cache_lock:
                            cache = read_json(_mcf, {})
                            cache[ck] = {"_cached_at": time.time(), "data": data}
                            write_json(_mcf, cache)
                    except Exception:
                        pass
                return data
        except Exception:
            if attempt < _retries - 1:
                time.sleep((attempt + 1) * 2)
    return None
