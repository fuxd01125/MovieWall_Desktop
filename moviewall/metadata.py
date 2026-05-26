"""Metadata provider — fetches TMDB + Douban data, stores separately in DB."""
import re
import time

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE, cache_lock
from moviewall.database import save_tmdb_meta, save_douban_meta, save_douban_season_meta
from moviewall.log import log
from moviewall.utils import normalize_key, tmdb_request, tmdb_image


# ── TMDB ────────────────────────────────────────────────────────────

_TMDB_MATCH_THRESHOLD = 50


def _tmdb_match_score(result, query_title, query_year, media_type, local_season_count=0):
    if not query_title:
        return 0
    score = 0
    q = normalize_key(query_title)

    candidates = set()
    for field in ("name", "original_name", "title", "original_title"):
        val = result.get(field)
        if val:
            candidates.add(normalize_key(val))

    if q in candidates:
        score += 100
    else:
        found_contains = False
        for c in candidates:
            if q in c or c in q:
                score += 60
                found_contains = True
                break
        if not found_contains:
            q_tokens = set(q.split())
            max_overlap = 0
            for c in candidates:
                c_tokens = set(c.split())
                overlap = len(q_tokens & c_tokens)
                if overlap > max_overlap:
                    max_overlap = overlap
            if q_tokens and max_overlap:
                score += int(max_overlap / len(q_tokens) * 40)

    result_date = result.get("first_air_date") or result.get("release_date") or ""
    result_year = result_date[:4] if len(result_date) >= 4 else ""
    if query_year and result_year:
        if query_year == result_year:
            score += 40
        else:
            score -= 20

    rtype = result.get("media_type") or ""
    if rtype and rtype == media_type:
        score += 20
    elif rtype and rtype != media_type:
        score -= 30

    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', query_title))
    orig_lang = result.get("original_language", "")
    if has_chinese and orig_lang == "zh":
        score += 15
    elif not has_chinese and orig_lang == "en":
        score += 10

    # Season count validation
    if local_season_count > 0:
        result_seasons = result.get("number_of_seasons")
        if result_seasons is None:
            s = result.get("seasons")
            if isinstance(s, (list, tuple)):
                result_seasons = len(s)
        if isinstance(result_seasons, (int, float)) and result_seasons > 0:
            diff = abs(local_season_count - result_seasons)
            if diff == 0:
                score += 25
            elif diff > 3:
                score -= 30
            elif diff > 1:
                score -= 15

    return max(0, score)


def _log_tmdb_search(query_title, query_year, media_type, results, scored, chosen):
    log.info("TMDB SEARCH: query=%s year=%s type=%s candidates=%d",
             query_title, query_year, media_type, len(scored))
    chosen_id = chosen.get("id") if chosen else None
    for s, r in scored[:8]:
        name = r.get("name") or r.get("title") or "?"
        orig = r.get("original_name") or r.get("original_title") or ""
        year = (r.get("first_air_date") or r.get("release_date") or "")[:4]
        sn = r.get("number_of_seasons") or len(r.get("seasons", [])) or "?"
        mark = " <<<" if r.get("id") == chosen_id else ""
        log.info("  candidate: score=%3d name=%s original=%s year=%s seasons=%s%s",
                 s, name, orig, year, sn, mark)
    if chosen:
        log.info("TMDB CHOSEN: id=%s name=%s score=%d",
                 chosen.get("id"), chosen.get("name") or chosen.get("title"),
                 scored[0][0] if scored else 0)


def _log_season_poster_chain(media_id, show_title, season_data, db_season_data):
    if season_data:
        for sn_str, sdata in season_data.items():
            poster = sdata.get("poster_url", "")
            log.info("TMDB SEASON POSTER: show=%s season=%s poster_url=%s",
                     show_title, sn_str, poster[:80] if poster else "(empty)")
    if db_season_data:
        for sn_str, sdata in db_season_data.items():
            poster = sdata.get("poster_url", "")
            log.info("TMDB SEASON POSTER (DB): show=%s season=%s poster_url=%s",
                     show_title, sn_str, poster[:80] if poster else "(empty)")


def clear_tmdb_cache(media_id, title):
    """Remove cached TMDB search entries matching this title from metadata_cache.json.
    Called at start of an update to force fresh TMDB lookup.
    Also clears raw API response cache (tmdb: prefix) so force_refresh
    actually fetches fresh data from TMDB instead of stale cached responses.
    Matches against both normalized title and the raw key prefix to handle
    different separators (underscore vs space in cache keys).
    """
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
        keys_to_delete = []
        nk = normalize_key(title)
        nk_alt = nk.replace(" ", "_")
        for k in list(cache.keys()):
            if k.startswith("tmdb:") or nk in k or nk_alt in k:
                keys_to_delete.append(k)
        for k in keys_to_delete:
            del cache[k]
        write_json(METADATA_CACHE_FILE, cache)
    if keys_to_delete:
        tmdb_count = sum(1 for k in keys_to_delete if k.startswith("tmdb:"))
        meta_count = len(keys_to_delete) - tmdb_count
        log.info("CLEAR CACHE: deleted %d entries for key=%s (tmdb_api=%d metadata=%d)",
                 len(keys_to_delete), nk, tmdb_count, meta_count)


def get_tmdb_metadata(title, year, media_type, force_refresh=False, local_season_count=0):
    cfg = load_config()
    if not cfg.get("metadata_enabled", True) or not (cfg.get("tmdb_api_key") or "").strip():
        return {}
    lang = cfg.get("tmdb_language", "zh-CN") or "zh-CN"
    key = f"{media_type}:{normalize_key(title)}:{year}:{lang}"

    if not force_refresh:
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            cached = cache.get(key)
        if cached and time.time() - cached.get("_cached_at", 0) < int(cfg.get("metadata_cache_days", 30)) * 86400:
            cached_data = cached.get("data", {})
            if not cached_data.get("tmdb_id"):
                # Empty cache entry — if force_refresh is not set, still skip
                # because we already know there's no match from a previous scan
                log.info("TMDB CACHE HIT (empty): key=%s", key)
                return {}
            fake = {
                "id": cached_data["tmdb_id"],
                "name": cached_data.get("title") or "",
                "original_name": cached_data.get("original_title") or "",
                "title": cached_data.get("title") or "",
                "original_title": cached_data.get("original_title") or "",
            }
            if cached_data.get("date"):
                fake["first_air_date"] = cached_data["date"]
            score = _tmdb_match_score(fake, title, year, media_type, local_season_count)
            if score >= _TMDB_MATCH_THRESHOLD:
                log.info("TMDB CACHE HIT: key=%s tmdb_id=%s score=%d", key, cached_data["tmdb_id"], score)
                return cached_data
            log.warning("TMDB CACHE STALE: key=%s cached_tmdb_id=%s score=%d — re-fetching",
                        key, cached_data["tmdb_id"], score)

    if force_refresh:
        log.info("TMDB FORCE REFRESH: key=%s", key)

    endpoint = "search/movie" if media_type == "movie" else "search/tv"
    params = {"query": title, "language": lang, "include_adult": "false", "page": 1}
    if year:
        params["year" if media_type == "movie" else "first_air_date_year"] = year
    results = (tmdb_request(endpoint, params) or {}).get("results") or []
    if not results:
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            cache[key] = {"_cached_at": time.time(), "data": {}}
            write_json(METADATA_CACHE_FILE, cache)
        log.info("TMDB SEARCH: query=%s → no results", title)
        return {}

    scored = [(_tmdb_match_score(r, title, year, media_type, local_season_count), r) for r in results]
    scored.sort(key=lambda x: x[0], reverse=True)

    best_score, best = scored[0]
    if best_score < _TMDB_MATCH_THRESHOLD:
        _log_tmdb_search(title, year, media_type, results, scored, None)
        with cache_lock:
            cache = read_json(METADATA_CACHE_FILE, {})
            cache[key] = {"_cached_at": time.time(), "data": {}}
            write_json(METADATA_CACHE_FILE, cache)
        log.info("TMDB SEARCH: query=%s — best=%d < threshold=%d, returning empty",
                 title, best_score, _TMDB_MATCH_THRESHOLD)
        return {}

    _log_tmdb_search(title, year, media_type, results, scored, best)

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
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
        cache[key] = {"_cached_at": time.time(), "data": data}
        write_json(METADATA_CACHE_FILE, cache)
    return data


def fetch_tmdb_seasons(tmdb_id, seasons_list, lang):
    """Fetch per-season TMDB metadata (rating, air_date, overview, poster).
    Falls back to en-US for overview when the preferred language has none.
    """
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
    season_map = {}
    for season in seasons_list:
        sn = season.get("season_number")
        if not sn:
            continue
        ck = f"season:{tmdb_id}:{sn}:{lang}"
        with cache_lock:
            cached = cache.get(ck)
            if cached and time.time() - cached.get("_cached_at", 0) < int(load_config().get("metadata_cache_days", 30)) * 86400:
                sdata = cached.get("data", {})
            else:
                sdata = None
        if sdata is None:
            sdata = tmdb_request(f"tv/{tmdb_id}/season/{sn}", {"language": lang}) or {}
            if sdata:
                with cache_lock:
                    cache = read_json(METADATA_CACHE_FILE, {})
                    cache[ck] = {"_cached_at": time.time(), "data": sdata}
        if sdata:
            entry = {}
            if sdata.get("vote_average"):
                entry["rating"] = sdata["vote_average"]
            if sdata.get("air_date"):
                entry["air_date"] = sdata["air_date"]
            overview = sdata.get("overview") or ""
            if not overview.strip() and lang != "en-US":
                en_ck = f"season:{tmdb_id}:{sn}:en-US"
                with cache_lock:
                    en_cached = cache.get(en_ck)
                    if en_cached and time.time() - en_cached.get("_cached_at", 0) < int(load_config().get("metadata_cache_days", 30)) * 86400:
                        en_sdata = en_cached.get("data", {})
                    else:
                        en_sdata = None
                if en_sdata is None:
                    en_sdata = tmdb_request(f"tv/{tmdb_id}/season/{sn}", {"language": "en-US"}) or {}
                    if en_sdata:
                        with cache_lock:
                            cache = read_json(METADATA_CACHE_FILE, {})
                            cache[en_ck] = {"_cached_at": time.time(), "data": en_sdata}
                if en_sdata:
                    en_overview = (en_sdata.get("overview") or "").strip()
                    if en_overview:
                        overview = en_overview
            if overview:
                entry["overview"] = overview
            if sdata.get("poster_path"):
                entry["poster_url"] = tmdb_image(sdata["poster_path"], "w500")
            if entry:
                season_map[str(sn)] = entry
    log.info("TMDB SEASONS: tmdb_id=%s seasons_fetched=%d poster_count=%d",
             tmdb_id, len(seasons_list), sum(1 for s in season_map.values() if s.get("poster_url")))
    return season_map


# ── Orchestrator ────────────────────────────────────────────────────

def _final_consistency_check(tmdb_data, query_title, query_year, media_type, local_season_count=0):
    if not tmdb_data or not tmdb_data.get("tmdb_id"):
        return False
    fake = {
        "id": tmdb_data["tmdb_id"],
        "name": tmdb_data.get("title") or "",
        "original_name": tmdb_data.get("original_title") or "",
        "title": tmdb_data.get("title") or "",
        "original_title": tmdb_data.get("original_title") or "",
    }
    if tmdb_data.get("date"):
        fake["first_air_date"] = tmdb_data["date"]
    score = _tmdb_match_score(fake, query_title, query_year, media_type, local_season_count)
    if score < _TMDB_MATCH_THRESHOLD:
        log.warning("CONSISTENCY FAILED: query=%s tmdb=%s score=%d — rejecting",
                    query_title, tmdb_data.get("title"), score)
        return False
    return True


def attach_all_metadata(item, force_refresh=False):
    """Fetch TMDB + Douban metadata for an item, store in DB.
    When force_refresh=True, always skips the metadata cache and clears old DB data.
    ALWAYS calls save_tmdb_meta() — even with empty — to clear stale metadata.
    """
    media_id = item["id"]
    media_type = "movie" if item.get("type") == "movie" else "tv"
    query_title = item.get("title", "")
    query_year = item.get("year", "")
    local_seasons = item.get("seasons") or []
    local_season_count = len(local_seasons)
    cfg = load_config()
    meta = {}

    from moviewall.douban import _douban_available
    douban_ok = cfg.get("douban_enabled", True) and _douban_available()

    # ── TMDB ─────────────────────────────────────────────────────
    log.info("ATTACH METADATA: media_id=%s title=%s force_refresh=%s",
             media_id, query_title, force_refresh)

    # Fetch TMDB — skip cache if force_refresh
    tmdb_data = get_tmdb_metadata(query_title, query_year, media_type,
                                  force_refresh=force_refresh,
                                  local_season_count=local_season_count)

    if tmdb_data:
        log.info("TMDB RESULT: title=%s tmdb_id=%s score=%s",
                 tmdb_data.get("title"), tmdb_data.get("tmdb_id"), "OK")

    # Final consistency check
    if not _final_consistency_check(tmdb_data, query_title, query_year, media_type, local_season_count):
        tmdb_data = {}

    season_data = {}
    if tmdb_data and tmdb_data.get("tmdb_id"):
        if media_type == "tv":
            lang = cfg.get("tmdb_language", "zh-CN") or "zh-CN"
            season_data = fetch_tmdb_seasons(tmdb_data["tmdb_id"], local_seasons, lang)

    # ALWAYS save — even empty clears stale data
    tmdb_store = dict(tmdb_data) if tmdb_data else {}
    if season_data:
        tmdb_store["_season_data"] = season_data
    save_tmdb_meta(media_id, tmdb_store)
    log.info("ATTACH SAVED: media_id=%s tmdb_id=%s season_count=%d",
             media_id, tmdb_store.get("tmdb_id"), len(season_data))

    if media_type == "tv" and season_data:
        from moviewall.database import load_tmdb_meta
        from_db = load_tmdb_meta(media_id)
        _log_season_poster_chain(media_id, query_title, season_data,
                                 (from_db.get("_season_data") or {}))

    if tmdb_data:
        meta["tmdb"] = dict(tmdb_data)
        if tmdb_data.get("title"):
            item["display_title"] = tmdb_data["title"]

    # ── Douban (show-level) ──────────────────────────────────────
    if douban_ok:
        from moviewall.douban import fetch_douban_meta, fetch_douban_by_id
        overrides = cfg.get("douban_id_overrides", {})
        override_id = overrides.get(media_id, "")
        if override_id:
            douban_data = fetch_douban_by_id(override_id)
        else:
            title_cn = tmdb_data.get("title", "") if tmdb_data else (item.get("display_title") or query_title)
            title_en = tmdb_data.get("original_title", "") if tmdb_data else ""
            douban_data = fetch_douban_meta(title_cn or title_en or query_title, query_year, media_type=media_type)

        if douban_data:
            save_douban_meta(media_id, douban_data)
            meta["douban"] = dict(douban_data)
            # Only use show-level Douban synopsis if TMDB has no overview at all
            if douban_data.get("synopsis") and tmdb_data and not tmdb_data.get("overview", "").strip():
                overview_override = dict(tmdb_data)
                overview_override["overview"] = douban_data["synopsis"]
                save_tmdb_meta(media_id, {**overview_override, "_season_data": season_data})

    item["metadata"] = meta

    # ── Douban per-season (for shows) ────────────────────────────
    if media_type == "tv" and douban_ok:
        from moviewall.douban import fetch_douban_by_season
        show_title = tmdb_data.get("title", "") if tmdb_data else query_title
        orig_title_show = tmdb_data.get("original_title", "") if tmdb_data else ""
        season_meta_db = {}
        for season in local_seasons:
            sn = season.get("season_number")
            if not sn:
                continue
            sdata = fetch_douban_by_season(show_title, query_year, sn, orig_title_show)
            if sdata:
                save_douban_season_meta(season["id"], media_id, sn, sdata)
                season_meta_db[str(sn)] = sdata
        if season_meta_db:
            item["_season_meta"] = season_meta_db

    return item
