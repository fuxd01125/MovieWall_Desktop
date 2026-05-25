"""Douban scraper — search, rating, synopsis, per-season support."""
import http.cookiejar
import json
import random
import re
import time
import urllib.parse
import urllib.request

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE
from moviewall.database import (
    save_douban_meta, save_douban_season_meta,
    load_douban_meta, load_douban_season_meta,
)

DOUBAN_SEARCH = "https://movie.douban.com/subject_search"
DOUBAN_HOME = "https://movie.douban.com/"
DOUBAN_MOBILE = "https://m.douban.com/movie/subject/{}/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
MOBILE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def _get_opener():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    try:
        opener.open(urllib.request.Request(DOUBAN_HOME, headers=HEADERS), timeout=15)
    except Exception:
        pass
    return opener


def _request(url, opener=None):
    cfg = load_config()
    time.sleep(float(cfg.get("douban_request_delay", 1.5)) + random.uniform(0, 0.5))
    if opener is None:
        opener = _get_opener()
    h = dict(HEADERS, Referer="https://movie.douban.com/")
    try:
        with opener.open(urllib.request.Request(url, headers=h), timeout=15) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _clean(s):
    return re.sub(r'[\u0000-\u001f\u200e\u200f\u2028\u2029]', '', s)


def _parse_items(html):
    m = re.search(r'window\.__DATA__\s*=\s*({.*?});', html, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(_clean(m.group(1))).get("items", [])
    except Exception:
        return []


def _year_from_title(text):
    m = re.search(r'(?:\(|（)(19|20)\d{2}(?:\)|）)', str(text))
    return m.group(1) if m else ""


def _pick_best(items, year):
    """Pick best matching item from douban search results."""
    # Filter: only movie/TV subjects
    valid = [i for i in items if i.get("tpl_name") in ("search_subject", None, "")]
    if not valid:
        return None
    # 1) try year match
    for item in valid:
        iy = item.get("year", "") or _year_from_title(item.get("title", ""))
        if year and iy and str(year) in str(iy):
            return item
    # 2) prefer item with a rating
    for item in valid:
        if item.get("rating", {}).get("value"):
            return item
    return valid[0]


def _search(title, year):
    """Search douban, return best matching item dict or None."""
    opener = _get_opener()
    candidates = [title]
    stripped = re.sub(r'[：:（(][^)）]*[)）]', '', title).strip()
    if stripped and stripped != title:
        candidates.append(stripped)

    for t in candidates:
        if not t:
            continue
        for cat in ("1002", ""):
            params = {"search_text": t}
            if cat:
                params["cat"] = cat
            url = DOUBAN_SEARCH + "?" + urllib.parse.urlencode(params)
            html = _request(url, opener)
            if not html:
                continue
            items = _parse_items(html)
            if not items:
                continue
            best = _pick_best(items, year)
            if best:
                return best
    return None


def _parse_rating(item):
    r = item.get("rating") or {}
    rating = r.get("value")
    return {
        "douban_id": item.get("id", ""),
        "rating": float(rating) if rating else None,
        "star_count": r.get("star_count"),
        "rating_count": r.get("count"),
        "abstract": item.get("abstract", ""),
        "abstract_2": item.get("abstract_2", ""),
    }


# ── Public API ──────────────────────────────────────────────────────

def fetch_douban_meta(title, year):
    """Fetch Douban rating + abstract for a movie/show. Returns dict or None."""
    cache = read_json(METADATA_CACHE_FILE, {})
    key = f"douban:{urllib.parse.quote(title)}:{year or ''}"
    cached = cache.get(key)
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        result = cached["data"]
    else:
        item = _search(title, year)
        if item:
            result = _parse_rating(item)
        else:
            result = None
        cache[key] = {"_cached_at": time.time(), "data": result}
        write_json(METADATA_CACHE_FILE, cache)

    # Always try synopsis
    if result and result.get("douban_id"):
        syn = _fetch_synopsis(result["douban_id"])
        if syn:
            result["synopsis"] = syn
    return result


def fetch_douban_by_id(douban_id):
    """Fetch Douban data for a known ID."""
    cache = read_json(METADATA_CACHE_FILE, {})
    ck = f"douban_id:{douban_id}"
    cached = cache.get(ck)
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        result = cached["data"]
    else:
        item = _search(douban_id, "")
        result = _parse_rating(item) if item else None
        cache[ck] = {"_cached_at": time.time(), "data": result}
        write_json(METADATA_CACHE_FILE, cache)

    if result and result.get("douban_id"):
        syn = _fetch_synopsis(result["douban_id"])
        if syn:
            result["synopsis"] = syn
    return result


def fetch_douban_by_season(show_title, show_year, season_number):
    """Search Douban for a specific season of a show.
       e.g. "葬送的芙莉莲 第二季" or "Hannibal Season 2"
    """
    keywords = [f"{show_title} 第{season_number}季", f"{show_title} Season {season_number}"]
    for kw in keywords:
        item = _search(kw, show_year)
        if item:
            return _parse_rating(item)
    return None


def _fetch_synopsis(douban_id):
    """Fetch plot synopsis from mobile Douban page."""
    cache = read_json(METADATA_CACHE_FILE, {})
    ck = f"synopsis:{douban_id}"
    cached = cache.get(ck)
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        return cached["data"]

    time.sleep(float(cfg.get("douban_request_delay", 1.5)) + random.uniform(0, 0.5))
    url = DOUBAN_MOBILE.format(douban_id)
    synopsis = None
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=dict(MOBILE_HEADERS, Referer="https://m.douban.com/")),
            timeout=15,
        ) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            # Main synopsis
            m = re.search(r'<section[^>]*class="subject-intro"[^>]*>(.*?)</section>', html, re.DOTALL)
            if m:
                m2 = re.search(r'<p[^>]*>(.*?)</p>', m.group(1), re.DOTALL)
                if m2:
                    synopsis = re.sub(r'<[^>]+>', '', m2.group(1)).strip()
                    synopsis = re.sub(r'\s+', ' ', synopsis)
            # Fallback: meta description
            if not synopsis:
                m = re.search(r'<meta name="description"[^>]*content="([^"]*)"', html)
                if m:
                    desc = m.group(1)
                    si = desc.find('简介：')
                    if si >= 0:
                        synopsis = desc[si+3:].strip()
    except Exception:
        pass
    cache[ck] = {"_cached_at": time.time(), "data": synopsis}
    write_json(METADATA_CACHE_FILE, cache)
    return synopsis


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
