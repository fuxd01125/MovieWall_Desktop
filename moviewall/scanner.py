"""Scanner — walks media folders, updates database."""
import re
from pathlib import Path

from moviewall.config import load_config, APP_DIR
from moviewall.constants import VIDEO_EXTS
from moviewall.utils import (
    stable_id, clean_title, parse_year, parse_season_number, parse_episode_number,
    pretty_season, pretty_episode, generate_video_image, ffmpeg_exe,
)
from moviewall.artwork import find_movie_poster, find_show_poster, find_season_poster, find_episode_thumb
from moviewall.metadata import attach_all_metadata
from moviewall.database import (
    upsert_media, upsert_season, upsert_episode, delete_all_media,
)


def _folder_mtime(folder):
    try:
        return folder.stat().st_mtime if folder.exists() else 0
    except OSError:
        return 0


def _scan_movies(folder, cat_key, cat_name):
    """Scan movies from a category folder. Returns list of item dicts."""
    items = []
    dirs = [p for p in folder.iterdir() if p.is_dir()]
    loose = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO_EXTS]

    for movie_folder in dirs:
        videos = sorted(
            [p for p in movie_folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS],
            key=lambda p: p.name.lower(),
        )
        if not videos:
            continue
        main = max(videos, key=lambda p: p.stat().st_size if p.exists() else 0)
        title = clean_title(movie_folder.name)
        year = parse_year(movie_folder.name)
        item_id = stable_id("movie", main.resolve())
        poster = find_movie_poster(movie_folder, title, main)
        thumb = poster or generate_video_image(
            main, APP_DIR / "static" / "generated" / "thumbs" / f"{item_id}.jpg",
            int(load_config().get("thumbnail_second", 60)),
        )
        item = {
            "id": item_id, "type": "movie", "category_key": cat_key, "category_name": cat_name,
            "title": title, "display_title": title, "year": year,
            "folder": str(movie_folder.resolve()), "path": str(main.resolve()),
            "filename": main.name, "poster": poster, "thumb": thumb,
        }
        upsert_media(item)
        items.append(item)

    for video in loose:
        title = clean_title(video.name)
        year = parse_year(video.name)
        item_id = stable_id("movie", video.resolve())
        poster = find_movie_poster(video.parent, title, video)
        thumb = poster or generate_video_image(
            video, APP_DIR / "static" / "generated" / "thumbs" / f"{item_id}.jpg",
            int(load_config().get("thumbnail_second", 60)),
        )
        item = {
            "id": item_id, "type": "movie", "category_key": cat_key, "category_name": cat_name,
            "title": title, "display_title": title, "year": year,
            "folder": str(video.parent.resolve()), "path": str(video.resolve()),
            "filename": video.name, "poster": poster, "thumb": thumb,
        }
        upsert_media(item)
        items.append(item)

    return items


def _scan_shows(folder, cat_key, cat_name):
    """Scan TV shows from a category folder. Returns list of item dicts."""
    shows = []
    dirs = [p for p in folder.iterdir() if p.is_dir()]

    for show_folder in dirs:
        season_dirs = [p for p in show_folder.iterdir()
                       if p.is_dir() and re.search(r"Season\s*\d+", p.name, flags=re.I)]
        if not season_dirs:
            season_dirs = [show_folder]

        show_title = clean_title(show_folder.name)
        show_year = parse_year(show_folder.name)
        show_id = stable_id("show", show_folder.resolve())
        seasons = []

        for season_folder in season_dirs:
            sn = parse_season_number(season_folder.name)
            videos = sorted(
                [p for p in season_folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS],
                key=lambda p: (parse_episode_number(p.name), p.name.lower()),
            )
            if not videos:
                continue
            season_id = stable_id("season", season_folder.resolve(), sn)
            episodes = []
            for idx, video in enumerate(videos):
                epn = parse_episode_number(video.name) or (idx + 1)
                ep_id = stable_id("episode", video.resolve())
                thumb = find_episode_thumb(video, show_title, sn, epn)
                if not thumb:
                    thumb = generate_video_image(
                        video, APP_DIR / "static" / "generated" / "thumbs" / f"{ep_id}.jpg",
                        int(load_config().get("thumbnail_second", 60)),
                    )
                ep = {
                    "id": ep_id, "show_id": show_id, "season_id": season_id,
                    "season_number": sn, "episode_number": epn,
                    "title": pretty_episode(epn), "filename": video.name,
                    "path": str(video.resolve()), "folder": str(video.parent.resolve()),
                    "thumb": thumb,
                }
                episodes.append(ep)

            season_poster = find_season_poster(season_folder, show_title, sn) or \
                            (episodes[0].get("thumb") if episodes else None)
            season = {
                "id": season_id, "show_id": show_id, "season_number": sn,
                "title": pretty_season(sn), "folder": str(season_folder.resolve()),
                "poster": season_poster, "episode_count": len(episodes), "episodes": episodes,
            }
            seasons.append(season)

        if not seasons:
            continue

        show_poster = find_show_poster(show_folder, show_title) or seasons[0].get("poster")
        total_eps = sum(len(s["episodes"]) for s in seasons)
        show_item = {
            "id": show_id, "type": "show", "category_key": cat_key, "category_name": cat_name,
            "title": show_title, "display_title": show_title, "year": show_year,
            "folder": str(show_folder.resolve()), "poster": show_poster,
            "season_count": len(seasons), "episode_count": total_eps, "seasons": seasons,
        }
        # Persist core data to DB
        upsert_media(show_item)
        for s in seasons:
            upsert_season(show_id, s)
            for ep in s["episodes"]:
                upsert_episode(show_id, s["id"], ep)

        shows.append(show_item)

    return shows


def scan_library(progress_callback=None):
    """Main scan entry point. Returns library dict."""
    cfg = load_config()
    root = Path(cfg.get("library_root", "")).expanduser()
    if not root.exists():
        return {"items": [], "stats": {}, "error": f"根目录不存在：{root}"}

    from moviewall.config import normalize_categories
    categories = normalize_categories()
    stats = {"movies": 0, "shows": 0, "episodes": 0}

    # Wipe DB media — we re-insert everything fresh
    delete_all_media()

    total_cats = len([c for c in categories.values() if (root / c).exists() if isinstance(list(categories.keys())[0], str)]) or 1
    # Actually count real folders
    existing_cats = [(fn, cat) for fn, cat in categories.items() if (root / fn).exists()]
    total = len(existing_cats)

    all_items = []
    for idx, (folder_name, cat) in enumerate(existing_cats):
        folder = root / folder_name
        display = cat["name"]
        if progress_callback:
            progress_callback(idx / total if total else 0, f"扫描: {display}")

        if cat.get("type") == "movie":
            cat_items = _scan_movies(folder, folder_name, display)
        else:
            cat_items = _scan_shows(folder, folder_name, display)

        # Attach metadata (TMDB + Douban → DB separate)
        for i, item in enumerate(cat_items):
            if progress_callback:
                progress_callback((idx + (i + 1) / len(cat_items)) / total if total else 0,
                                  f"获取元数据: {item.get('display_title') or item.get('title')}")
            attach_all_metadata(item)

        all_items.extend(cat_items)

    stats["movies"] = sum(1 for i in all_items if i["type"] == "movie")
    stats["shows"] = sum(1 for i in all_items if i["type"] == "show")
    stats["episodes"] = sum(
        len(s["episodes"]) for i in all_items if i["type"] == "show" for s in i.get("seasons", [])
    )

    if progress_callback:
        progress_callback(1.0, "扫描完成")
    return {"items": all_items, "stats": stats}
