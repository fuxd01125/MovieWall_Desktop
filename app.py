import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts", ".m2ts", ".webm", ".rmvb"}
ART_EXTS = [".jpg", ".jpeg", ".png", ".webp"]
POSTER_NAMES = ["poster", "cover", "folder", "default", "movie", "show", "海报", "封面", "主图"]
SEASON_POSTER_NAMES = ["poster", "cover", "folder", "season", "海报", "封面", "季海报"]
THUMB_NAMES = ["thumb", "thumbnail", "landscape", "backdrop", "fanart", "screenshot", "still", "剧照", "缩略图", "截图"]
ART_HINTS = [
    "poster", "cover", "folder", "default", "movie", "show", "season",
    "thumb", "thumbnail", "landscape", "backdrop", "fanart",
    "海报", "封面", "剧照", "缩略图", "图片", "主图", "背景", "横图", "竖图"
]
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"


def runtime_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = runtime_dir()
CONFIG_FILE = APP_DIR / "config.json"
LIBRARY_FILE = APP_DIR / "library.json"
METADATA_CACHE_FILE = APP_DIR / "metadata_cache.json"
LOCAL_METADATA_FILE = APP_DIR / "local_metadata.json"

app = Flask(__name__, template_folder=str(APP_DIR / "templates"), static_folder=str(APP_DIR / "static"))


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


def stable_id(*parts):
    raw = "||".join(str(p) for p in parts)
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]


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


def art_name_key(text: str):
    return normalize_key(text)


def image_files(folder: Path, recursive=False):
    if not folder.exists() or not folder.is_dir():
        return []
    try:
        it = folder.rglob("*") if recursive else folder.iterdir()
        return [p for p in it if p.is_file() and p.suffix.lower() in ART_EXTS]
    except Exception:
        return []


def score_image_candidate(path: Path, preferred_names):
    name_raw = safe_stem(path.name).lower()
    name_key = art_name_key(path.name)
    preferred_keys = [art_name_key(x) for x in preferred_names if x]
    score = 0
    if name_key in preferred_keys:
        score += 160
    name_tokens = set(name_key.split())
    for key in preferred_keys:
        if not key:
            continue
        key_tokens = set(key.split())
        if key in name_key or name_key in key:
            score += 75
        overlap = len(name_tokens & key_tokens)
        if overlap:
            score += overlap * 18
    for hint in ART_HINTS:
        h = hint.lower()
        if h in name_raw or h in name_key:
            score += 55
    if any(x in name_raw or x in name_key for x in ["poster", "cover", "folder", "海报", "封面", "主图", "竖图"]):
        score += 50
    if re.search(r"\b[sS]\d{1,2}[eE]\d{1,3}\b", name_raw):
        score -= 100
    try:
        score += min(int(path.stat().st_mtime) % 1000, 999) / 1000
    except Exception:
        pass
    return score


def score_episode_thumb_candidate(path: Path, preferred_names):
    name_raw = safe_stem(path.name).lower()
    name_key = art_name_key(path.name)
    if any(x in name_raw or x in name_key for x in ["poster", "cover", "folder", "season", "海报", "封面"]):
        return -1000
    preferred_keys = [art_name_key(x) for x in preferred_names if x]
    score = 0
    if name_key in preferred_keys:
        score += 150
    for key in preferred_keys:
        if key and (key in name_key or name_key in key):
            score += 75
    for hint in THUMB_NAMES:
        if hint.lower() in name_raw or hint.lower() in name_key:
            score += 55
    return score


def first_existing_art(candidates):
    seen = set()
    for c in candidates:
        if not c:
            continue
        p = Path(c)
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        if p.exists() and p.is_file() and p.suffix.lower() in ART_EXTS:
            return str(p.resolve())
    return None


def art_candidates_by_names(folder: Path, names):
    out = []
    for name in names:
        if not name:
            continue
        for ext in ART_EXTS:
            out.append(folder / f"{name}{ext}")
    return out


def flexible_art_candidates(folder: Path, preferred_names=None, recursive=False, allow_any=True):
    preferred_names = [x for x in (preferred_names or []) if x]
    candidates = []
    candidates += art_candidates_by_names(folder, preferred_names)
    imgs = image_files(folder, recursive=recursive)
    scored = sorted(imgs, key=lambda p: score_image_candidate(p, preferred_names + ART_HINTS), reverse=True)
    candidates += [p for p in scored if score_image_candidate(p, preferred_names + ART_HINTS) >= 40]
    if allow_any:
        candidates += scored
    return candidates


def static_poster_candidates(*names):
    return flexible_art_candidates(APP_DIR / "static" / "posters", list(names), recursive=False, allow_any=False)


def find_movie_poster(movie_folder: Path, movie_title: str, video_path: Path):
    preferred = [*POSTER_NAMES, movie_folder.name, movie_title, safe_stem(video_path.name), "海报", "封面", "主图"]
    candidates = []
    candidates += [video_path.with_suffix(ext) for ext in ART_EXTS]
    candidates += [movie_folder.parent / f"{movie_folder.name}{ext}" for ext in ART_EXTS]
    candidates += flexible_art_candidates(movie_folder, preferred, recursive=False, allow_any=True)
    candidates += flexible_art_candidates(movie_folder, preferred, recursive=True, allow_any=False)
    candidates += static_poster_candidates(movie_folder.name, movie_title, safe_stem(video_path.name))
    return first_existing_art(candidates)


def find_show_poster(show_folder: Path, show_title: str):
    preferred = [*POSTER_NAMES, show_folder.name, show_title, "海报", "封面", "主图", "剧集", "电视剧", "series"]
    candidates = []
    candidates += [show_folder.parent / f"{show_folder.name}{ext}" for ext in ART_EXTS]
    candidates += flexible_art_candidates(show_folder, preferred, recursive=False, allow_any=True)
    candidates += flexible_art_candidates(show_folder, preferred, recursive=True, allow_any=False)
    candidates += static_poster_candidates(show_folder.name, show_title)
    return first_existing_art(candidates)


def find_season_poster(season_folder: Path, show_title: str, season_number: int):
    preferred = [*SEASON_POSTER_NAMES, season_folder.name, f"{show_title} Season {season_number:02d}", f"{show_title} S{season_number:02d}", f"第{season_number:02d}季", "海报", "封面", "季海报"]
    candidates = []
    candidates += [season_folder.parent / f"{season_folder.name}{ext}" for ext in ART_EXTS]
    candidates += flexible_art_candidates(season_folder, preferred, recursive=False, allow_any=True)
    candidates += flexible_art_candidates(season_folder, preferred, recursive=True, allow_any=False)
    candidates += static_poster_candidates(season_folder.name, f"{show_title} S{season_number:02d}")
    return first_existing_art(candidates)


def find_episode_thumb(video_path: Path, show_title: str, season_number: int, episode_number: int):
    preferred = [safe_stem(video_path.name), f"{show_title} S{season_number:02d}E{episode_number:02d}", f"S{season_number:02d}E{episode_number:02d}", f"E{episode_number:02d}", *THUMB_NAMES]
    candidates = []
    candidates += [video_path.with_suffix(ext) for ext in ART_EXTS]
    imgs = image_files(video_path.parent, recursive=False)
    scored = sorted(imgs, key=lambda p: score_episode_thumb_candidate(p, preferred), reverse=True)
    candidates += [p for p in scored if score_episode_thumb_candidate(p, preferred) >= 40]
    selected = first_existing_art(candidates)
    if selected and any(x in Path(selected).stem.lower() for x in ["poster", "cover", "folder", "season", "海报", "封面"]):
        return None
    return selected


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


def get_tmdb_metadata(title, year, media_type):
    cfg = load_config()
    if not cfg.get("metadata_enabled", True) or not (cfg.get("tmdb_api_key") or "").strip():
        return {}
    lang = cfg.get("tmdb_language", "zh-CN") or "zh-CN"
    cache = read_json(METADATA_CACHE_FILE, {})
    key = f"{media_type}:{normalize_key(title)}:{year}:{lang}"
    cached = cache.get(key)
    if cached and time.time() - cached.get("_cached_at", 0) < int(cfg.get("metadata_cache_days", 30)) * 86400:
        return cached.get("data", {})
    endpoint = "search/movie" if media_type == "movie" else "search/tv"
    params = {"query": title, "language": lang, "include_adult": "false", "page": 1}
    if year:
        params["year" if media_type == "movie" else "first_air_date_year"] = year
    results = (tmdb_request(endpoint, params) or {}).get("results") or []
    if not results:
        cache[key] = {"_cached_at": time.time(), "data": {}}
        write_json(METADATA_CACHE_FILE, cache)
        return {}
    best = results[0]
    tmdb_id = best.get("id")
    details_endpoint = f"movie/{tmdb_id}" if media_type == "movie" else f"tv/{tmdb_id}"
    details = tmdb_request(details_endpoint, {"language": lang}) or {}
    data = {
        "source": "TMDB",
        "tmdb_id": tmdb_id,
        "title": details.get("title") or details.get("name") or best.get("title") or best.get("name") or title,
        "original_title": details.get("original_title") or details.get("original_name") or "",
        "overview": details.get("overview") or best.get("overview") or "",
        "rating": details.get("vote_average") or best.get("vote_average") or "",
        "date": details.get("release_date") or details.get("first_air_date") or "",
        "genres": [g.get("name") for g in details.get("genres", []) if g.get("name")],
        "poster_url": tmdb_image(details.get("poster_path") or best.get("poster_path"), "w500"),
        "backdrop_url": tmdb_image(details.get("backdrop_path") or best.get("backdrop_path"), "w1280"),
    }
    cache[key] = {"_cached_at": time.time(), "data": data}
    write_json(METADATA_CACHE_FILE, cache)
    return data


def get_local_metadata(item_id, title, folder):
    local = read_json(LOCAL_METADATA_FILE, {"items": {}}).get("items", {})
    keys = [item_id, title, Path(folder).name if folder else "", normalize_key(title), normalize_key(Path(folder).name if folder else "")]
    for k in keys:
        if k and k in local:
            return local[k]
    return {}


def attach_metadata(item):
    media_type = "movie" if item.get("type") == "movie" else "tv"
    tmdb = get_tmdb_metadata(item.get("title", ""), item.get("year", ""), media_type)
    local = get_local_metadata(item.get("id"), item.get("title"), item.get("folder"))
    meta = {}
    if tmdb:
        meta["tmdb"] = tmdb
        if tmdb.get("title"):
            item["display_title"] = tmdb["title"]
    if local:
        meta["local"] = local
        if local.get("douban"):
            meta["douban"] = local["douban"]
    item["metadata"] = meta
    return item


def scan_movies_category(category_folder: Path, category_key: str, category_name: str):
    items = []
    for movie_folder in sorted([p for p in category_folder.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        videos = sorted([p for p in movie_folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS], key=lambda p: p.name.lower())
        if not videos:
            continue
        main = max(videos, key=lambda p: p.stat().st_size if p.exists() else 0)
        title = clean_title(movie_folder.name)
        year = parse_year(movie_folder.name)
        item_id = stable_id("movie", main.resolve())
        poster = find_movie_poster(movie_folder, title, main)
        thumb = poster or generate_video_image(main, APP_DIR / "static" / "generated" / "thumbs" / f"{item_id}.jpg", int(load_config().get("thumbnail_second", 60)))
        items.append(attach_metadata({
            "id": item_id, "type": "movie", "category_key": category_key, "category_name": category_name,
            "title": title, "display_title": title, "year": year, "folder": str(movie_folder.resolve()),
            "path": str(main.resolve()), "filename": main.name, "poster": poster, "thumb": thumb
        }))
    for video in sorted([p for p in category_folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS], key=lambda p: p.name.lower()):
        title = clean_title(video.name)
        year = parse_year(video.name)
        item_id = stable_id("movie", video.resolve())
        poster = find_movie_poster(video.parent, title, video)
        thumb = poster or generate_video_image(video, APP_DIR / "static" / "generated" / "thumbs" / f"{item_id}.jpg", int(load_config().get("thumbnail_second", 60)))
        items.append(attach_metadata({
            "id": item_id, "type": "movie", "category_key": category_key, "category_name": category_name,
            "title": title, "display_title": title, "year": year, "folder": str(video.parent.resolve()),
            "path": str(video.resolve()), "filename": video.name, "poster": poster, "thumb": thumb
        }))
    return items


def scan_show_category(category_folder: Path, category_key: str, category_name: str):
    shows = []
    for show_folder in sorted([p for p in category_folder.iterdir() if p.is_dir()], key=lambda p: p.name.lower()):
        show_title = clean_title(show_folder.name)
        show_year = parse_year(show_folder.name)
        show_id = stable_id("show", show_folder.resolve())
        season_dirs = [p for p in show_folder.iterdir() if p.is_dir() and re.search(r"Season\s*\d+", p.name, flags=re.I)]
        if not season_dirs:
            season_dirs = [show_folder]
        seasons = []
        for season_folder in sorted(season_dirs, key=lambda p: parse_season_number(p.name)):
            sn = parse_season_number(season_folder.name)
            videos = sorted([p for p in season_folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS], key=lambda p: (parse_episode_number(p.name), p.name.lower()))
            if not videos:
                continue
            season_id = stable_id("season", season_folder.resolve(), sn)
            episodes = []
            for video in videos:
                epn = parse_episode_number(video.name)
                ep_id = stable_id("episode", video.resolve())
                thumb = find_episode_thumb(video, show_title, sn, epn)
                if not thumb:
                    thumb = generate_video_image(video, APP_DIR / "static" / "generated" / "thumbs" / f"{ep_id}.jpg", int(load_config().get("thumbnail_second", 60)))
                episodes.append({
                    "id": ep_id, "type": "episode", "title": pretty_episode(epn), "episode_number": epn,
                    "season_number": sn, "filename": video.name, "path": str(video.resolve()),
                    "folder": str(video.parent.resolve()), "thumb": thumb
                })
            season_poster = find_season_poster(season_folder, show_title, sn) or (episodes[0].get("thumb") if episodes else None)
            seasons.append({
                "id": season_id, "type": "season", "season_number": sn, "title": pretty_season(sn),
                "folder": str(season_folder.resolve()), "poster": season_poster,
                "episode_count": len(episodes), "episodes": episodes
            })
        if not seasons:
            continue
        show_poster = find_show_poster(show_folder, show_title) or seasons[0].get("poster")
        total_eps = sum(len(s["episodes"]) for s in seasons)
        shows.append(attach_metadata({
            "id": show_id, "type": "show", "category_key": category_key, "category_name": category_name,
            "title": show_title, "display_title": show_title, "year": show_year, "folder": str(show_folder.resolve()),
            "poster": show_poster, "season_count": len(seasons), "episode_count": total_eps, "seasons": seasons
        }))
    return shows


def scan_library():
    cfg = load_config()
    root = Path(cfg.get("library_root", "")).expanduser()
    categories = cfg.get("categories", {"Movies": "电影", "TV Shows": "剧集", "Anime": "动漫"})
    stats = {"root": str(root), "movies": 0, "shows": 0, "episodes": 0, "categories": {}, "ffmpeg_available": bool(ffmpeg_exe()), "tmdb_enabled": bool((cfg.get("tmdb_api_key") or "").strip())}
    items = []
    if not root.exists():
        data = {"items": [], "stats": stats, "error": f"影视根目录不存在：{root}"}
        save_library(data)
        return data
    for folder_name, display in categories.items():
        folder = root / folder_name
        if not folder.exists():
            continue
        items.extend(scan_movies_category(folder, folder_name, display) if folder_name.lower() == "movies" else scan_show_category(folder, folder_name, display))
    stats["movies"] = sum(1 for i in items if i["type"] == "movie")
    stats["shows"] = sum(1 for i in items if i["type"] == "show")
    stats["episodes"] = sum(len(s["episodes"]) for i in items if i["type"] == "show" for s in i["seasons"])
    for i in items:
        k = i["category_key"]
        stats["categories"].setdefault(k, {"name": i["category_name"], "count": 0})
        stats["categories"][k]["count"] += 1
    items.sort(key=lambda x: (x.get("display_title") or x.get("title", "")).lower())
    data = {"items": items, "stats": stats}
    save_library(data)
    return data


def iter_media_items():
    for item in load_library().get("items", []):
        yield item
        if item.get("type") == "show":
            for season in item.get("seasons", []):
                yield season
                for ep in season.get("episodes", []):
                    yield ep


def find_media_by_id(media_id):
    for item in iter_media_items():
        if item.get("id") == media_id:
            return item
    return None


def is_allowed_media_path(path: str):
    try:
        target = str(Path(path).resolve())
    except Exception:
        return False
    for item in iter_media_items():
        if item.get("path"):
            try:
                if str(Path(item["path"]).resolve()) == target:
                    return True
            except Exception:
                pass
    return False


def is_allowed_folder(folder: str):
    try:
        target = str(Path(folder).resolve())
    except Exception:
        return False
    for item in iter_media_items():
        if item.get("folder"):
            try:
                if str(Path(item["folder"]).resolve()) == target:
                    return True
            except Exception:
                pass
    return False


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/library")
def api_library():
    return jsonify(load_library())


@app.route("/api/scan", methods=["POST"])
def api_scan():
    return jsonify(scan_library())


@app.route("/api/artwork/<media_id>/<kind>")
def api_artwork(media_id, kind):
    item = find_media_by_id(media_id)
    if not item:
        abort(404)
    art_path = item.get(kind)
    if not art_path:
        abort(404)
    p = Path(art_path)
    if not p.exists() or not p.is_file():
        abort(404)
    return send_file(str(p))


@app.route("/api/play", methods=["POST"])
def api_play():
    data = request.get_json(force=True)
    media_path = data.get("path")
    if not media_path or not is_allowed_media_path(media_path):
        abort(403)
    potplayer = load_config().get("potplayer_path", "")
    if not Path(potplayer).exists():
        return jsonify({"ok": False, "error": "PotPlayer 路径不存在，请检查 config.json"}), 400
    try:
        subprocess.Popen([potplayer, media_path], shell=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/open_folder", methods=["POST"])
def api_open_folder():
    folder = request.get_json(force=True).get("folder")
    if not folder or not is_allowed_folder(folder):
        abort(403)
    if os.name == "nt":
        subprocess.Popen(["explorer", str(Path(folder).resolve())])
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "仅支持 Windows Explorer"}), 400


if __name__ == "__main__":
    import threading, webbrowser
    if load_config().get("auto_open_browser", True):
        threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000/")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
