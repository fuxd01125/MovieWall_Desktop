import re
from pathlib import Path

from moviewall.config import load_config, save_library, APP_DIR
from moviewall.constants import VIDEO_EXTS
from moviewall.utils import stable_id, clean_title, parse_year, parse_season_number, parse_episode_number, pretty_season, pretty_episode, generate_video_image, ffmpeg_exe
from moviewall.artwork import find_movie_poster, find_show_poster, find_season_poster, find_episode_thumb
from moviewall.metadata import attach_metadata


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
