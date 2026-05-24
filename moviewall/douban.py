import http.cookiejar
import json
import random
import re
import time
import urllib.parse
import urllib.request

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE

DOUBAN_SEARCH_URL = "https://movie.douban.com/subject_search"
DOUBAN_HOME_URL = "https://movie.douban.com/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _get_opener():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    # Visit homepage first to get session cookie (bid)
    req = urllib.request.Request(DOUBAN_HOME_URL, headers=HEADERS)
    try:
        opener.open(req, timeout=15)
    except Exception:
        pass
    return opener


def _request(url, opener=None):
    cfg = load_config()
    delay = float(cfg.get("douban_request_delay", 1.5))
    time.sleep(delay + random.uniform(0, 0.5))
    if opener is None:
        opener = _get_opener()
    headers = dict(HEADERS, Referer="https://movie.douban.com/")
    req = urllib.request.Request(url, headers=headers)
    try:
        with opener.open(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _clean_json(raw):
    """Remove control characters that break json.loads."""
    return re.sub(r'[\u0000-\u001f\u200e\u200f\u2028\u2029]', '', raw)


def _parse_search_data(html):
    """Parse window.__DATA__ from search results page."""
    m = re.search(r'window\.__DATA__\s*=\s*({.*?});', html, re.DOTALL)
    if not m:
        return []
    try:
        raw = _clean_json(m.group(1))
        data = json.loads(raw)
        return data.get("items", [])
    except Exception:
        return []


def search_and_fetch(title_cn, title_en, year):
    """Search Douban by title, extract rating and id from search results JSON."""
    opener = _get_opener()
    candidates = [title_cn, title_en] if title_en else [title_cn]

    for t in candidates:
        if not t:
            continue
        params = {"search_text": t, "cat": "1002"}
        url = DOUBAN_SEARCH_URL + "?" + urllib.parse.urlencode(params)
        html = _request(url, opener)
        if not html:
            continue

        items = _parse_search_data(html)
        if not items:
            continue

        best = None
        for item in items:
            item_year = item.get("year", "")
            if year and item_year and str(year) in str(item_year):
                best = item
                break

        if best is None:
            best = items[0]

        douban_id = best.get("id", "")
        if not douban_id:
            continue

        rating_info = best.get("rating", {}) or {}
        rating = rating_info.get("value", "")
        star_count = rating_info.get("star_count", "")

        abstract = best.get("abstract", "") or ""
        abstract_2 = best.get("abstract_2", "") or ""
        synopsis = abstract + (" · " + abstract_2 if abstract_2 else "")

        result = {"douban_id": douban_id}
        if rating:
            result["rating"] = float(rating)
        if star_count:
            result["star_count"] = float(star_count)
        if abstract:
            result["synopsis"] = synopsis

        return result

    return None


def get_douban_metadata(title_cn, title_en, year, media_type):
    cfg = load_config()
    if not cfg.get("douban_enabled", True):
        return None

    cache = read_json(METADATA_CACHE_FILE, {})
    search_key = f"douban:{urllib.parse.quote(title_cn)}:{year or ''}"
    cached = cache.get(search_key)

    if cached and time.time() - cached.get("_cached_at", 0) < int(cfg.get("metadata_cache_days", 30)) * 86400:
        return cached.get("data")

    try:
        result = search_and_fetch(title_cn, title_en, year)
    except Exception:
        result = None

    cache[search_key] = {"_cached_at": time.time(), "data": result}
    write_json(METADATA_CACHE_FILE, cache)
    return result


def get_douban_metadata_by_id(douban_id):
    """Fetch Douban metadata by manually provided ID, with caching."""
    cache = read_json(METADATA_CACHE_FILE, {})
    cache_key = f"douban_id:{douban_id}"
    cached = cache.get(cache_key)
    cfg = load_config()
    if cached and time.time() - cached.get("_cached_at", 0) < int(cfg.get("metadata_cache_days", 30)) * 86400:
        return cached.get("data")

    # For a known ID, search by that ID on douban
    url = DOUBAN_SEARCH_URL + "?" + urllib.parse.urlencode({"search_text": douban_id, "cat": "1002"})
    opener = _get_opener()
    html = _request(url, opener)
    result = None
    if html:
        items = _parse_search_data(html)
        for item in items:
            if item.get("id") == douban_id:
                rating_info = item.get("rating", {}) or {}
                rating = rating_info.get("value", "")
                abstract = item.get("abstract", "") or ""
                result = {"douban_id": douban_id}
                if rating:
                    result["rating"] = float(rating)
                if abstract:
                    result["synopsis"] = abstract
                break

    cache[cache_key] = {"_cached_at": time.time(), "data": result}
    write_json(METADATA_CACHE_FILE, cache)
    return result


def set_douban_id_override(media_id, douban_id):
    from moviewall.config import load_config as _lc, write_json as _wj, CONFIG_FILE as _cf
    cfg = _lc()
    overrides = cfg.get("douban_id_overrides", {})
    if douban_id:
        overrides[media_id] = str(douban_id)
    else:
        overrides.pop(media_id, None)
    cfg["douban_id_overrides"] = overrides
    _wj(_cf, cfg)
