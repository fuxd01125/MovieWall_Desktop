"""Metadata provider — fetches TMDB + Douban data, stores separately in DB."""
import time

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE
from moviewall.database import save_tmdb_meta, save_douban_meta, save_douban_season_meta
from moviewall.utils import normalize_key, tmdb_request, tmdb_image


# ── TMDB ────────────────────────────────────────────────────────────

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
        "source": "TMDB", "tmdb_id": tmdb_id,
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


def fetch_tmdb_seasons(tmdb_id, seasons_list, lang):
    """Fetch per-season TMDB metadata (rating, air_date, overview)."""
    cache = read_json(METADATA_CACHE_FILE, {})
    season_map = {}
    for season in seasons_list:
        sn = season.get("season_number")
        if not sn:
            continue
        ck = f"season:{tmdb_id}:{sn}:{lang}"
        cached = cache.get(ck)
        if cached and time.time() - cached.get("_cached_at", 0) < int(load_config().get("metadata_cache_days", 30)) * 86400:
            sdata = cached.get("data", {})
        else:
            sdata = tmdb_request(f"tv/{tmdb_id}/season/{sn}", {"language": lang}) or {}
            if sdata:
                cache[ck] = {"_cached_at": time.time(), "data": sdata}
        if sdata:
            rating = sdata.get("vote_average")
            air_date = sdata.get("air_date", "")
            overview = sdata.get("overview", "")
            if rating:
                season_map[str(sn)] = {"rating": rating, "air_date": air_date, "overview": overview}
    write_json(METADATA_CACHE_FILE, cache)
    return season_map


# ── Orchestrator ────────────────────────────────────────────────────

def attach_all_metadata(item):
    """Fetch TMDB + Douban metadata for an item, store both in DB separately.
       Returns the item dict with metadata references populated (for API compatibility).
    """
    media_id = item["id"]
    media_type = "movie" if item.get("type") == "movie" else "tv"
    cfg = load_config()
    meta = {}

    # ── TMDB ─────────────────────────────────────────────────────
    tmdb_data = get_tmdb_metadata(item.get("title", ""), item.get("year", ""), media_type)
    if tmdb_data:
        # Store in DB separately
        season_data = {}
        if item.get("type") == "show" and tmdb_data.get("tmdb_id"):
            lang = cfg.get("tmdb_language", "zh-CN") or "zh-CN"
            season_data = fetch_tmdb_seasons(tmdb_data["tmdb_id"], item.get("seasons", []), lang)
        tmdb_store = dict(tmdb_data)
        if season_data:
            tmdb_store["_season_data"] = season_data
        save_tmdb_meta(media_id, tmdb_store)

        # Attach to item for API
        meta["tmdb"] = tmdb_data
        if tmdb_data.get("title"):
            item["display_title"] = tmdb_data["title"]

    # ── Douban (show-level) ──────────────────────────────────────
    if cfg.get("douban_enabled", True):
        from moviewall.douban import fetch_douban_meta, fetch_douban_by_id
        overrides = cfg.get("douban_id_overrides", {})
        override_id = overrides.get(media_id, "")
        if override_id:
            douban_data = fetch_douban_by_id(override_id)
        else:
            title_cn = tmdb_data.get("title", "") if tmdb_data else (item.get("display_title") or item.get("title", ""))
            title_en = tmdb_data.get("original_title", "") if tmdb_data else ""
            year = item.get("year", "")
            douban_data = fetch_douban_meta(title_cn or title_en or item.get("title", ""), year)

        if douban_data:
            save_douban_meta(media_id, douban_data)
            meta["douban"] = douban_data
            if douban_data.get("synopsis") and tmdb_data:
                tmdb_data["overview"] = douban_data["synopsis"]

    item["metadata"] = meta

    # ── Douban per-season (for shows) ────────────────────────────
    if item.get("type") == "show" and cfg.get("douban_enabled", True):
        from moviewall.douban import fetch_douban_by_season
        show_title = tmdb_data.get("title", "") if tmdb_data else item.get("title", "")
        show_year = item.get("year", "")
        season_meta = {}
        for season in item.get("seasons", []):
            sn = season.get("season_number")
            if not sn:
                continue
            sdata = fetch_douban_by_season(show_title, show_year, sn)
            if sdata and sdata.get("rating"):
                save_douban_season_meta(season["id"], media_id, sn, sdata)
                season_meta[str(sn)] = sdata
        if season_meta:
            item["_season_meta"] = season_meta

    return item
