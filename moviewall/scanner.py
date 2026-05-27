"""Scanner — walks media folders, updates database.
Now uses dynamic category detection: media_type (movie/show) is auto-detected
from file structure, not from hardcoded category names.
"""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from moviewall.config import load_config, APP_DIR, normalize_categories
from moviewall.constants import VIDEO_EXTS
from moviewall.log import log, Timer
from moviewall.utils import (
    stable_id, clean_title, parse_year, parse_season_number, parse_episode_number,
    pretty_season, pretty_episode, generate_video_image,
)
from moviewall.artwork import find_movie_poster, find_show_poster, find_season_poster, find_episode_thumb
from moviewall.metadata import attach_all_metadata
from moviewall.database import (
    upsert_media_batch, upsert_season_batch, upsert_episode_batch, delete_all_media, delete_media, get_conn,
)


def _folder_mtime(folder):
    try:
        return folder.stat().st_mtime if folder.exists() else 0
    except OSError:
        return 0


def _cleanup_orphaned_entries(scanned_items):
    """Remove DB entries whose folder path no longer exists on disk.
    Handles folder rename, move, and deletion scenarios.
    Scanned items have 'folder' pointing to current paths; anything
    in DB with a folder that doesn't exist is an orphan.
    """
    scanned_folders = set()
    for item in scanned_items:
        f = item.get("folder")
        if f:
            scanned_folders.add(str(Path(f).resolve()))
    # Also include all episode-level folders from scanned shows
    for item in scanned_items:
        if item.get("type") == "show":
            for season in item.get("seasons", []):
                for ep in season.get("episodes", []):
                    ef = ep.get("folder")
                    if ef:
                        scanned_folders.add(str(Path(ef).resolve()))

    orphans = []
    conn = get_conn()
    try:
        rows = conn.execute("SELECT id, folder FROM media WHERE folder IS NOT NULL").fetchall()
        for row in rows:
            folder = row["folder"]
            folder_key = str(Path(folder).resolve()) if folder else ""
            if folder_key and folder_key not in scanned_folders and not Path(folder_key).exists():
                log.info("Removing orphan: %s (folder no longer exists: %s)", row["id"], folder_key)
                orphans.append(row["id"])
    except Exception:
        pass
    finally:
        conn.close()
    # Delete orphans outside the query connection to avoid nesting issues
    for orphan_id in orphans:
        try:
            delete_media(orphan_id)
        except Exception:
            log.error("Failed to delete orphan: %s", orphan_id)


def _detect_show_folder(folder, cat_name=""):
    """Auto-detect if a subdirectory looks like a TV show based on file structure.
    Returns True if season subdirectories or episode-numbered filenames are found.
    Considers multiple detection signals: season dirs, episode patterns, multi-video count.
    """
    folder_name = folder.name
    # Signal 1: season subdirectories
    for p in folder.iterdir():
        if not p.is_dir():
            continue
        if re.search(r"Season\s*\d+", p.name, flags=re.I):
            log.info("[SCAN] category=%s folder=%s detected_type=show reason=Season dir: %s", cat_name, folder_name, p.name)
            return True
        if re.search(r"第\s*\d+\s*季", p.name):
            log.info("[SCAN] category=%s folder=%s detected_type=show reason=Season dir: %s", cat_name, folder_name, p.name)
            return True
        if re.search(r"第\s*[一二三四五六七八九十]+\s*季", p.name):
            log.info("[SCAN] category=%s folder=%s detected_type=show reason=Season dir: %s", cat_name, folder_name, p.name)
            return True

    # Signal 2: episode number patterns in filenames (S01E01, E01, 第X集, etc.)
    videos = [p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    if not videos:
        log.info("[SCAN] category=%s folder=%s detected_type=unknown reason=no video files found", cat_name, folder_name)
        return False

    ep_count = sum(1 for v in videos if parse_episode_number(v.name) > 0)
    total = len(videos)

    # Multiple videos with episode patterns → show
    if total > 1 and ep_count >= total * 0.5:
        log.info("[SCAN] category=%s folder=%s detected_type=show reason=%d/%d files have episode patterns", cat_name, folder_name, ep_count, total)
        return True

    # Single video with episode pattern → show (e.g. Running Man with S01E01 only)
    if total == 1 and ep_count > 0:
        log.info("[SCAN] category=%s folder=%s detected_type=show reason=single file with episode pattern: %s", cat_name, folder_name, videos[0].name)
        return True

    # Multiple videos, but few/no episode patterns → check structure
    if total >= 3:
        log.info("[SCAN] category=%s folder=%s detected_type=show reason=%d video files (multi-file heuristic)", cat_name, folder_name, total)
        return True

    log.info("[SCAN] category=%s folder=%s detected_type=movie reason=ep_count=%d/%d no season dirs", cat_name, folder_name, ep_count, total)
    return False


def _scan_single_movie(subfolder, cat_key, cat_name, videos=None):
    """Scan a single movie subdirectory. Returns item dict or None."""
    if videos is None:
        videos = sorted(
            [p for p in subfolder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS],
            key=lambda p: p.name.lower(),
        )
    if not videos:
        return None
    main = max(videos, key=lambda p: p.stat().st_size if p.exists() else 0)
    title = clean_title(subfolder.name)
    year = parse_year(subfolder.name)
    item_id = stable_id("movie", main.resolve())
    poster = find_movie_poster(subfolder, title, main)
    thumb = poster or generate_video_image(
        main, APP_DIR / "static" / "generated" / "thumbs" / f"{item_id}.jpg",
        int(load_config().get("thumbnail_second", 60)),
    )
    return {
        "id": item_id, "type": "movie", "category_key": cat_key, "category_name": cat_name,
        "title": title, "display_title": title, "year": year,
        "folder": str(subfolder.resolve()), "path": str(main.resolve()),
        "filename": main.name, "poster": poster, "thumb": thumb,
    }


def _scan_single_show(show_folder, cat_key, cat_name):
    """Scan a single TV show folder (with season detection). Returns show item dict or None."""
    season_dirs = _detect_season_folders(show_folder)
    show_title = clean_title(show_folder.name)
    show_year = parse_year(show_folder.name)
    show_id = stable_id("show", show_folder.resolve())
    seasons = []

    for season_folder in season_dirs:
        sn = parse_season_number(season_folder.name)
        videos = sorted(
            [p for p in season_folder.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXTS],
            key=_episode_sort_key,
        )
        if not videos:
            log.info("SKIP SEASON (no videos): show=%s folder=%s", show_title, season_folder.name)
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
        return None

    show_poster = find_show_poster(show_folder, show_title) or seasons[0].get("poster")
    total_eps = sum(len(s["episodes"]) for s in seasons)
    show_item = {
        "id": show_id, "type": "show", "category_key": cat_key, "category_name": cat_name,
        "title": show_title, "display_title": show_title, "year": show_year,
        "folder": str(show_folder.resolve()), "poster": show_poster,
        "season_count": len(seasons), "episode_count": total_eps, "seasons": seasons,
    }
    all_seasons = []
    all_episodes = []
    for s in seasons:
        s["show_id"] = show_id
        all_seasons.append(s)
        for ep in s["episodes"]:
            ep["show_id"] = show_id
            ep["season_id"] = s["id"]
            all_episodes.append(ep)

    upsert_media_batch([show_item])
    if all_seasons:
        upsert_season_batch(all_seasons)
    if all_episodes:
        upsert_episode_batch(all_episodes)
    return show_item


def _detect_season_folders(show_folder):
    """Detect season subdirectories supporting both English and Chinese naming.
    Returns list of Path objects. Falls back to show_folder itself if no season dirs found.
    """
    season_dirs = []
    for p in show_folder.iterdir():
        if not p.is_dir():
            continue
        if re.search(r"Season\s*\d+", p.name, flags=re.I):
            season_dirs.append(p)
        elif re.search(r"第\s*\d+\s*季", p.name):
            season_dirs.append(p)
        elif re.search(r"第\s*[一二三四五六七八九十]+\s*季", p.name):
            season_dirs.append(p)
    if not season_dirs:
        season_dirs = [show_folder]
    season_dirs.sort(key=lambda p: parse_season_number(p.name))
    return season_dirs


def _episode_sort_key(p):
    """Sort by episode number first, then by filename for deterministic order.
    Returns (ep_number, 0, name) for parsed or (999999, 1, name) for fallback.
    """
    epn = parse_episode_number(p.name)
    if epn:
        return (epn, 0, p.name.lower())
    return (999999, 1, p.name.lower())


def _scan_category(folder, cat_key, cat_name):
    """Scan a single category folder with auto media_type detection.
    Each subdirectory is independently classified as movie or show based on file structure.
    Loose video files in the category root are treated as movies.
    Shows are upserted inside _scan_single_show; movies are batch-upserted here.
    """
    items = []
    dirs = sorted([p for p in folder.iterdir() if p.is_dir()], key=lambda p: p.name.lower())

    movie_items = []
    for subfolder in dirs:
        if _detect_show_folder(subfolder, cat_name):
            item = _scan_single_show(subfolder, cat_key, cat_name)
        else:
            item = _scan_single_movie(subfolder, cat_key, cat_name)
            if item:
                movie_items.append(item)
                items.append(item)

    # Batch upsert all subfolder-based movies
    if movie_items:
        upsert_media_batch(movie_items)

    # Loose video files in category root → always movie
    loose = [p for p in folder.iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
    loose_movies = []
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
        loose_movies.append(item)

    if loose_movies:
        upsert_media_batch(loose_movies)
        items.extend(loose_movies)

    return items


def scan_library(progress_callback=None):
    """Main scan entry point. Uses dynamic category detection.
    All category folder keys from config are auto-discovered — no hardcoded names.
    """
    cfg = load_config()
    root = Path(cfg.get("library_root", "")).expanduser()
    if not root.exists():
        return {"items": [], "stats": {}, "error": f"根目录不存在：{root}"}

    categories = normalize_categories()
    t = Timer("scan_library")
    t.__enter__()
    stats = {"movies": 0, "shows": 0, "episodes": 0}

    from moviewall.database import get_conn
    root_mtime = _folder_mtime(root)
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM metadata_tracker WHERE key='last_scan_mtime'").fetchone()
        last_mtime = float(row["value"]) if row else 0
    except Exception:
        last_mtime = 0
    finally:
        conn.close()

    full_rebuild = root_mtime == 0 or root_mtime > last_mtime + 86400 or last_mtime == 0

    if full_rebuild:
        delete_all_media()
        log.info("Full scan: root mtime changed (%.0f vs %.0f)", root_mtime, last_mtime)
    else:
        log.info("Incremental scan skipped: no mtime change since last scan")

    existing_cats = [(fn, cat) for fn, cat in categories.items() if (root / fn).exists()]
    total = len(existing_cats)

    all_items = []
    for idx, (folder_name, cat) in enumerate(existing_cats):
        folder = root / folder_name
        display = cat["name"]
        log.info("[SCAN] category=%s folder_key=%s path=%s", display, folder_name, str(folder))
        if progress_callback:
            progress_callback(idx / total if total else 0, f"扫描: {display}")

        cat_items = _scan_category(folder, folder_name, display)
        log.info("[SCAN] category=%s scanned=%d items (movies=%d shows=%d)",
                 display, len(cat_items),
                 sum(1 for i in cat_items if i["type"] == "movie"),
                 sum(1 for i in cat_items if i["type"] == "show"))

        if cat_items:
            max_workers = min(5, len(cat_items))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(attach_all_metadata, item): item for item in cat_items}
                done = 0
                for future in as_completed(futures):
                    done += 1
                    if progress_callback:
                        item = futures[future]
                        progress_callback((idx + done / len(cat_items)) / total if total else 0,
                                          f"元数据: {item.get('display_title') or item.get('title')}")
                    try:
                        future.result()
                    except Exception:
                        pass

        all_items.extend(cat_items)

    stats["movies"] = sum(1 for i in all_items if i["type"] == "movie")
    stats["shows"] = sum(1 for i in all_items if i["type"] == "show")
    stats["episodes"] = sum(
        len(s["episodes"]) for i in all_items if i["type"] == "show" for s in i.get("seasons", [])
    )

    _cleanup_orphaned_entries(all_items)

    if full_rebuild:
        try:
            conn2 = get_conn()
            conn2.execute("INSERT OR REPLACE INTO metadata_tracker (key,value) VALUES ('last_scan_mtime',?)",
                          (str(root_mtime),))
            conn2.commit()
            conn2.close()
        except Exception:
            pass

    if progress_callback:
        progress_callback(1.0, "扫描完成")
    t.__exit__(None, None, None)
    return {"items": all_items, "stats": stats}
