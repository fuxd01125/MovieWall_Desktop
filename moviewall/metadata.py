import time
from pathlib import Path

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE, LOCAL_METADATA_FILE
from moviewall.utils import normalize_key, tmdb_request, tmdb_image


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
