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

from moviewall.config import load_config, METADATA_CACHE_FILE
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
    title = re.sub(r"\[[^\]]+\]", " ", title)
    title = re.sub(r"\b(1080p|2160p|720p|480p|4K|BluRay|WEB-DL|WEBRip|HDRip|DVDRip|BDRip|HDR|HEVC|x265|x264|AAC|DDP5\.1|H\.264|H\.265)\b", " ", title, flags=re.I)
    title = re.sub(r"\b[Ss]\d{1,2}[Ee]\d{1,3}\b", " ", title)
    title = re.sub(r"(?<!\d)[_\-]+(?!\d)", " ", title)
    title = re.sub(r"\.(?!\s*\d)", " ", title)
    title = re.sub(r"\s+", " ", title).strip()
    return title or safe_stem(text)


def parse_year(text: str):
    m = re.search(r"\((19|20)\d{2}\)", str(text))
    return m.group(0).strip("()") if m else ""


def parse_season_number(text: str):
    m = re.search(r"Season\s*(\d+)", str(text), flags=re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"[Ss](\d{1,2})", str(text))
    if m:
        return int(m.group(1))
    return 1


def parse_episode_number(text: str):
    m = re.search(r"[Ss]\d{1,2}[Ee](\d{1,3})", str(text))
    if m:
        return int(m.group(1))
    m = re.search(r"[Ee](\d{1,3})", str(text))
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


def tmdb_request(endpoint, params):
    cfg = load_config()
    key = (cfg.get("tmdb_api_key") or "").strip()
    if not key:
        return None
    params = dict(params or {})
    params["api_key"] = key
    url = f"https://api.themoviedb.org/3/{endpoint}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "MovieWall/12"}), timeout=12) as resp:
            return json.loads(resp.read().decode("utf-8")) if resp.status == 200 else None
    except Exception:
        return None
