import re
from pathlib import Path

from moviewall.config import load_config, save_library, load_library, APP_DIR, normalize_categories
from moviewall.constants import VIDEO_EXTS
from moviewall.utils import stable_id, clean_title, parse_year, parse_season_number, parse_episode_number, pretty_season, pretty_episode, generate_video_image, ffmpeg_exe
from moviewall.artwork import find_movie_poster, find_show_poster, find_season_poster, find_episode_thumb
from moviewall.metadata import attach_metadata


def _folder_mtime(folder: Path):
    try:
        return folder.stat().st_mtime if folder.exists() else 0
    except OSError:
        return 0


def _build_item_map(items):
    m = {}
    for item in items:
        f = item.get("folder", "")
        if f:
            m[f] = item
        p = item.get("path", "")
        if p and p != f:
            m[p] = item
        if item.get("type") == "show":
            for s in item.get("seasons", []):
                sf = s.get("folder", "")
                if sf:
                    m[sf] = s
    return m


def _changed_folders(folders, mtimes):
    """Split folders into (changed, unchanged) based on mtime cache."""
    changed, unchanged = [], []
    for f in sorted(folders, key=lambda p: p.name.lower()):
        key = str(f.resolve())
        old = mtimes.get(key, 0)
        cur = _folder_mtime(f)
        if cur > old or cur == 0:
            changed.append(f)
        else:
            unchanged.append((key, cur))
    return changed, unchanged


def scan_movies_category(category_folder, category_key, category_name, mtimes, item_map):
    items = []
    new_mtimes = {}

    dirs = [p for p in category_folder.iterdir() if p.is_dir()]
    changed_dirs, unchanged = _changed_folders(dirs, mtimes)
    for key, cur in unchanged:
        if key in item_map:
            items.append(item_map[key])
        new_mtimes[key] = cur

    loose = [p for p in category_folder.iterdir() if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    changed_loose, unchanged_loose = _changed_folders(loose, mtimes)
    for key, cur in unchanged_loose:
        if key in item_map:
            items.append(item_map[key])
        new_mtimes[key] = cur

    for movie_folder in changed_dirs:
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
        new_mtimes[str(movie_folder.resolve())] = _folder_mtime(movie_folder)

    for video in changed_loose:
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
        new_mtimes[str(video.resolve())] = _folder_mtime(video)

    return items, new_mtimes


def scan_show_category(category_folder, category_key, category_name, mtimes, item_map):
    shows = []
    new_mtimes = {}

    dirs = [p for p in category_folder.iterdir() if p.is_dir()]
    for show_folder in sorted(dirs, key=lambda p: p.name.lower()):
        show_key = str(show_folder.resolve())
        season_dirs = [p for p in show_folder.iterdir() if p.is_dir() and re.search(r"Season\s*\d+", p.name, flags=re.I)]
        if not season_dirs:
            season_dirs = [show_folder]

        all_folders = [show_folder] + season_dirs
        any_changed = any(_folder_mtime(f) > mtimes.get(str(f.resolve()), 0) for f in all_folders)

        if not any_changed and show_key in item_map:
            shows.append(item_map[show_key])
            for f in all_folders:
                new_mtimes[str(f.resolve())] = _folder_mtime(f)
            continue

        show_title = clean_title(show_folder.name)
        show_year = parse_year(show_folder.name)
        show_id = stable_id("show", show_folder.resolve())
        seasons = []
        for season_folder in sorted(season_dirs, key=lambda p: parse_season_number(p.name)):
            sn = parse_season_number(season_folder.name)
            videos = sorted([p for p in season_folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS], key=lambda p: (parse_episode_number(p.name), p.name.lower()))
            if not videos:
                continue
            season_id = stable_id("season", season_folder.resolve(), sn)
            episodes = []
            for idx, video in enumerate(videos):
                epn = parse_episode_number(video.name) or (idx + 1)
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
            new_mtimes[str(season_folder.resolve())] = _folder_mtime(season_folder)

        if not seasons:
            continue
        show_poster = find_show_poster(show_folder, show_title) or seasons[0].get("poster")
        total_eps = sum(len(s["episodes"]) for s in seasons)
        shows.append(attach_metadata({
            "id": show_id, "type": "show", "category_key": category_key, "category_name": category_name,
            "title": show_title, "display_title": show_title, "year": show_year, "folder": str(show_folder.resolve()),
            "poster": show_poster, "season_count": len(seasons), "episode_count": total_eps, "seasons": seasons
        }))
        new_mtimes[show_key] = _folder_mtime(show_folder)

    return shows, new_mtimes


def scan_library(force=False):
    cfg = load_config()
    root = Path(cfg.get("library_root", "")).expanduser()
    categories = normalize_categories()
    stats = {"root": str(root), "movies": 0, "shows": 0, "episodes": 0, "categories": {}, "ffmpeg_available": bool(ffmpeg_exe()), "tmdb_enabled": bool((cfg.get("tmdb_api_key") or "").strip())}
    items = []
    all_mtimes = {}

    if not root.exists():
        data = {"items": [], "stats": stats, "error": f"影视根目录不存在：{root}"}
        save_library(data)
        return data

    old_data = load_library()
    old_mtimes = old_data.get("_scan_mtimes", {}) if not force else {}
    item_map = _build_item_map(old_data.get("items", []))

    for folder_name, cat in categories.items():
        folder = root / folder_name
        if not folder.exists():
            continue
        display = cat["name"]
        if cat.get("type") == "movie":
            cat_items, cat_mtimes = scan_movies_category(folder, folder_name, display, old_mtimes, item_map)
        else:
            cat_items, cat_mtimes = scan_show_category(folder, folder_name, display, old_mtimes, item_map)
        items.extend(cat_items)
        all_mtimes.update(cat_mtimes)

    stats["movies"] = sum(1 for i in items if i["type"] == "movie")
    stats["shows"] = sum(1 for i in items if i["type"] == "show")
    stats["episodes"] = sum(len(s["episodes"]) for i in items if i["type"] == "show" for s in i["seasons"])
    for i in items:
        k = i["category_key"]
        stats["categories"].setdefault(k, {"name": i["category_name"], "count": 0})
        stats["categories"][k]["count"] += 1
    items.sort(key=lambda x: (x.get("display_title") or x.get("title", "")).lower())
    data = {"items": items, "stats": stats, "_scan_mtimes": all_mtimes}
    save_library(data)
    return data
