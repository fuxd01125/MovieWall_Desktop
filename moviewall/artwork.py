import re
from pathlib import Path

from moviewall.config import APP_DIR
from moviewall.constants import ART_EXTS, POSTER_NAMES, SEASON_POSTER_NAMES, THUMB_NAMES, ART_HINTS
from moviewall.utils import safe_stem, normalize_key


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
