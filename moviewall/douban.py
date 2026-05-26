"""Douban scraper — search, rating, synopsis, per-season support.
Implements circuit breaker: after HTTP 403, disables all Douban requests for 24h.
"""
import http.cookiejar
import json
import random
import re
import ssl
import threading
import time
import urllib.parse
import urllib.error
import urllib.request

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE, cache_lock
from moviewall.log import log

# Use certifi CA bundle for consistent SSL behavior in debug & EXE mode
try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CONTEXT = ssl.create_default_context()

DOUBAN_SEARCH = "https://movie.douban.com/subject_search"
DOUBAN_HOME = "https://movie.douban.com/"
DOUBAN_MOBILE = "https://m.douban.com/movie/subject/{}/"

# ── Circuit breaker ──────────────────────────────────────────────────

_DOUBAN_BLOCKED_KEY = "douban_health"
_BLOCK_COOLDOWN_403 = 86400       # 24h after HTTP 403
_BLOCK_COOLDOWN_TIMEOUT = 3600    # 1h after timeout
_BLOCK_COOLDOWN_NETWORK = 1800    # 30min after network failure

# In-memory cache for _douban_available() — avoids repeated file reads
_available_cache = {"available": None, "timestamp": 0}
_available_cache_lock = threading.Lock()
_AVAILABLE_CACHE_TTL = 60  # seconds

def _douban_health():
    """Return (blocked, reason, blocked_until) for current Douban provider state."""
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
        h = cache.get(_DOUBAN_BLOCKED_KEY)
    if not h:
        return False, "", 0
    now = time.time()
    blocked_until = h.get("blocked_until", 0)
    if now < blocked_until:
        return True, h.get("reason", "unknown"), blocked_until
    return False, "", 0

def _set_douban_blocked(reason="blocked"):
    """Mark Douban provider as blocked with cooldown."""
    now = time.time()
    reason_lower = reason.lower()
    if "403" in reason_lower or "blocked" in reason_lower:
        cooldown = _BLOCK_COOLDOWN_403
    elif "timeout" in reason_lower:
        cooldown = _BLOCK_COOLDOWN_TIMEOUT
    else:
        cooldown = _BLOCK_COOLDOWN_NETWORK
    blocked_until = now + cooldown
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
        cache[_DOUBAN_BLOCKED_KEY] = {
            "blocked_at": now,
            "blocked_until": blocked_until,
            "reason": reason,
            "failure_count": cache.get(_DOUBAN_BLOCKED_KEY, {}).get("failure_count", 0) + 1,
        }
        write_json(METADATA_CACHE_FILE, cache)
    with _available_cache_lock:
        _available_cache["available"] = False
        _available_cache["timestamp"] = now
    log.warning("Douban provider blocked (cooldown=%.1fh, reason=%s)", cooldown / 3600, reason)

def _douban_available():
    """Early-exit check: returns False if Douban provider is in cooldown."""
    now = time.time()
    with _available_cache_lock:
        if _available_cache["available"] is not None and now - _available_cache["timestamp"] < _AVAILABLE_CACHE_TTL:
            return _available_cache["available"]
    blocked, reason, until = _douban_health()
    if blocked:
        result = False
    elif not load_config().get("douban_enabled", True):
        result = False
    else:
        result = True
    with _available_cache_lock:
        _available_cache["available"] = result
        _available_cache["timestamp"] = now
    return result

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
    ctx = _SSL_CONTEXT
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ctx),
        urllib.request.HTTPCookieProcessor(cj),
    )
    try:
        opener.open(urllib.request.Request(DOUBAN_HOME, headers=HEADERS), timeout=15)
    except Exception:
        pass
    return opener


def _request(url, opener=None):
    if not _douban_available():
        return None
    cfg = load_config()
    delay = float(cfg.get("douban_request_delay", 0.5)) + random.uniform(0, 0.3)
    time.sleep(delay)
    if opener is None:
        opener = _get_opener()
    h = dict(HEADERS, Referer="https://movie.douban.com/")
    try:
        with opener.open(urllib.request.Request(url, headers=h), timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
            if "登录重定向" in html or "检测到异常" in html:
                _set_douban_blocked("blocked: captcha detection")
                return None
            return html
    except urllib.error.HTTPError as e:
        if e.code == 403:
            _set_douban_blocked("HTTP 403")
        return None
    except Exception:
        _set_douban_blocked("network/timeout")
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


# ── Media type helpers ──────────────────────────────────────────────

def _get_item_type(item):
    """Return 'tv', 'movie', or None for a Douban search result item."""
    type_name = item.get("type_name") or item.get("type") or ""
    if type_name:
        t = type_name.lower().strip()
        if t in ("tv", "movie", "teleplay"):
            return "tv" if t == "teleplay" else t
    types = item.get("types")
    if isinstance(types, list) and len(types) > 0:
        pass
    return None


def _cn_digits(n):
    mapping = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}
    return mapping.get(n, str(n))


# ── Season matching ──────────────────────────────────────────────────

def _season_match_score(title, season_number):
    """Score how well a Douban title matches a specific season number."""
    if not title:
        return 0
    score = 0
    cn = re.search(rf'第({season_number}|[{_cn_digits(season_number)}])季', str(title))
    if cn:
        score += 100
    if re.search(rf'Season\s*{season_number}\b', str(title), re.I):
        score += 100
    if re.search(rf'\bS{season_number:02d}\b', str(title), re.I):
        score += 80
    if re.search(rf'\bS{season_number}\b', str(title), re.I):
        score += 60
    return score


# ── Search functions ─────────────────────────────────────────────────

def _pick_best(items, year, season_number=None, media_type=None):
    """Pick best matching item from douban search results.

    Rules:
    - TV type items are never matched to movie items (if type_name is available)
    - Season search requires explicit season mention in title (>0 score)
    - Year is a bonus for show-level, not a hard requirement
    - No fallback to show-level data for season searches
    """
    valid = [i for i in items if i.get("tpl_name") in ("search_subject", None, "")]
    if not valid:
        log.info("DOUBAN MATCH: no valid items (all filtered by tpl_name)")
        return None

    if media_type:
        before = len(valid)
        valid = [i for i in valid if _get_item_type(i) in (media_type, None)]
        filtered = before - len(valid)
        if filtered > 0:
            log.info("DOUBAN MATCH: filtered %d items by type=%s, %d remain", filtered, media_type, len(valid))

    if not valid:
        log.info("DOUBAN MATCH: no valid items after type filter")
        return None

    if season_number is not None:
        scored = [(item, _season_match_score(item.get("title", ""), season_number)) for item in valid]
        scored.sort(key=lambda x: x[1], reverse=True)
        best_score = scored[0][1]
        log.info("DOUBAN MATCH: season=%d best_score=%d candidates=%d",
                 season_number, best_score, len(scored))
        for s, item in scored[:5]:
            log.info("  candidate: score=%3d title=%s id=%s year=%s",
                     s, item.get("title", "?"), item.get("id", "?"),
                     item.get("year", "") or _year_from_title(item.get("title", "")))

        if best_score >= 80:
            return scored[0][0]
        log.info("DOUBAN MATCH: no season item with sufficient score (need >=80, got %d) → returning None", best_score)
        return None

    show_year = str(year) if year else ""
    year_filtered = []
    for item in valid:
        iy = item.get("year", "") or _year_from_title(item.get("title", ""))
        if show_year and iy and show_year in iy:
            year_filtered.append(item)

    if year_filtered:
        for item in year_filtered:
            if item.get("rating", {}).get("value"):
                return item
        return year_filtered[0]

    for item in valid:
        if item.get("rating", {}).get("value"):
            return item
    return valid[0]


def _search(title, year, season_number=None, media_type=None):
    """Search douban, return best matching item dict or None.
    Uses correct category: 1001=movie, 1002=tv.
    """
    opener = _get_opener()
    candidates = [title]
    stripped = re.sub(r'[：:（(][^)）]*[)）]', '', title).strip()
    if stripped and stripped != title:
        candidates.append(stripped)

    cat = "1001" if media_type == "movie" else "1002"

    for t in candidates:
        if not t:
            continue
        params = {"search_text": t, "cat": cat}
        url = DOUBAN_SEARCH + "?" + urllib.parse.urlencode(params)

        log.info("DOUBAN SEARCH: query=%s cat=%s season=%s type=%s",
                 t, cat, season_number, media_type)

        html = _request(url, opener)
        if not html:
            log.info("DOUBAN SEARCH: no response for query=%s", t)
            continue
        items = _parse_items(html)
        log.info("DOUBAN SEARCH: query=%s returned %d items", t, len(items))

        if not items:
            continue
        best = _pick_best(items, year, season_number, media_type)
        if best:
            log.info("DOUBAN MATCH: FINAL id=%s title=%s season=%s",
                     best.get("id", "?"), best.get("title", "?"), season_number)
            return best
    return None


def _search_raw(title):
    """Search douban and return ALL valid items (unfiltered). Used for season matching."""
    opener = _get_opener()
    params = {"search_text": title, "cat": "1002"}
    url = DOUBAN_SEARCH + "?" + urllib.parse.urlencode(params)

    log.info("DOUBAN RAW SEARCH: query=%s", title)

    html = _request(url, opener)
    if not html:
        return []
    items = _parse_items(html)

    log.info("DOUBAN RAW SEARCH: query=%s returned %d items", title, len(items))
    for item in items[:8]:
        log.info("  raw item: id=%s title=%s",
                 item.get("id", "?"), item.get("title", "?"))

    if not items:
        return []
    return [i for i in items if i.get("tpl_name") in ("search_subject", None, "")]


# ── Thread-safe cache operations ─────────────────────────────────

def _cache_get(key):
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
        return cache.get(key)

def _cache_set(key, value):
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
        cache[key] = value
        write_json(METADATA_CACHE_FILE, cache)


# ── Public API ──────────────────────────────────────────────────────

def fetch_douban_meta(title, year, media_type="tv"):
    """Fetch Douban rating + abstract for a movie/show. Returns dict or None."""
    if not _douban_available():
        return None
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    key = f"douban:{urllib.parse.quote(title)}:{year or ''}"
    cached = _cache_get(key)
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        result = cached["data"]
    else:
        item = _search(title, year, media_type=media_type)
        result = _parse_rating(item) if item else None
        _cache_set(key, {"_cached_at": time.time(), "data": result})

    if result and result.get("douban_id") and not result.get("synopsis"):
        syn = _fetch_synopsis(result["douban_id"])
        if syn:
            result["synopsis"] = syn
    return result


def fetch_douban_by_id(douban_id):
    """Fetch Douban data for a known ID."""
    if not _douban_available():
        return None
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    ck = f"douban_id:{douban_id}"
    cached = _cache_get(ck)
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        result = cached["data"]
    else:
        item = _search(douban_id, "")
        result = _parse_rating(item) if item else None
        _cache_set(ck, {"_cached_at": time.time(), "data": result})

    if result and result.get("douban_id"):
        syn = _fetch_synopsis(result["douban_id"])
        if syn:
            result["synopsis"] = syn
    return result


def _clear_mobile_cache_for_show(show_title):
    """Clear mobile detail cache entries that may contain this show's data."""
    with cache_lock:
        cache = read_json(METADATA_CACHE_FILE, {})
        keys = [k for k in cache if k.startswith("mobile:") or k.startswith("synopsis:")]
        # Only clear if there are relevant entries (we can't identify by show title,
        # so we clear all mobile caches during force refresh)
        for k in keys:
            del cache[k]
        if keys:
            write_json(METADATA_CACHE_FILE, cache)
            log.info("DOUBAN: cleared %d mobile cache entries for force refresh", len(keys))


def _fetch_mobile_detail(douban_id, force_refresh=False):
    """Fetch synopsis + poster + other details from mobile page."""
    if not _douban_available():
        return {}
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    ck = f"mobile:{douban_id}"
    if not force_refresh:
        cached = _cache_get(ck)
        if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
            return cached["data"]

    time.sleep(float(cfg.get("douban_request_delay", 0.5)) + random.uniform(0, 0.3))
    url = DOUBAN_MOBILE.format(douban_id)
    result = {}
    try:
        req = urllib.request.Request(url, headers=dict(MOBILE_HEADERS, Referer="https://m.douban.com/"))
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
            html = resp.read().decode("utf-8", errors="replace")

            m = re.search(r'<meta\s+property="og:image"[^>]*content="([^"]*)"', html)
            if m:
                result["poster_url"] = m.group(1)

            m = re.search(r'<section[^>]*class="subject-intro"[^>]*>(.*?)</section>', html, re.DOTALL)
            if m:
                m2 = re.search(r'<p[^>]*>(.*?)</p>', m.group(1), re.DOTALL)
                if m2:
                    synopsis = re.sub(r'<[^>]+>', '', m2.group(1)).strip()
                    synopsis = re.sub(r'\s+', ' ', synopsis)
                    if synopsis:
                        result["synopsis"] = synopsis
            if not result.get("synopsis"):
                m = re.search(r'<meta name="description"[^>]*content="([^"]*)"', html)
                if m:
                    desc = m.group(1)
                    si = desc.find('简介：')
                    if si >= 0:
                        result["synopsis"] = desc[si+3:].strip()

            m = re.search(r'<span[^>]*class="year"[^>]*>\(?(\d{4})\)?</span>', html)
            if m:
                result["air_date"] = m.group(1)

            m = re.search(r'<meta name="description"[^>]*content="([^"]*)"', html)
            if m:
                desc = m.group(1)
                si = desc.find('主演：')
                ei = desc.find('简介：')
                if si >= 0:
                    cast_text = desc[si+3:] if ei < 0 else desc[si+3:ei]
                    if cast_text.strip():
                        result["cast_info"] = cast_text.strip()

    except Exception:
        pass

    _cache_set(ck, {"_cached_at": time.time(), "data": result})
    return result


def _build_season_queries(show_title, season_number, original_title=""):
    """Build multiple search query candidates for a specific season."""
    cn = _cn_digits(season_number)
    queries = []

    queries.append(f"{show_title} 第{cn}季")
    queries.append(f"{show_title} 第{season_number}季")
    queries.append(f"{show_title} Season {season_number}")
    queries.append(f"{show_title} S{season_number:02d}")
    if original_title and original_title != show_title:
        queries.append(f"{original_title} 第{cn}季")
        queries.append(f"{original_title} Season {season_number}")
    queries.append(show_title)

    seen = set()
    unique = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def fetch_douban_by_season(show_title, show_year, season_number, original_title="", force_refresh=False):
    """Search Douban for a specific season of a show.

    CRITICAL: Never returns show-level data for season searches.
    Returns None if no season-specific page is found.
    When force_refresh=True, bypasses mobile detail page cache.
    """
    if not _douban_available():
        return None

    queries = _build_season_queries(show_title, season_number, original_title)

    log.info("DOUBAN SEASON: show=%s season=%d force_refresh=%s queries=%s",
             show_title, season_number, force_refresh, queries)

    best_item = None
    best_score = -1

    for query in queries:
        is_exact = "第" in query or "Season" in query or "S{:02d}".format(season_number) in query
        # Force refresh: clear mobile detail cache for this show before searching
        if force_refresh:
            _clear_mobile_cache_for_show(show_title)
        item = _search(query, show_year, season_number, media_type="tv")
        if item:
            score = _season_match_score(item.get("title", ""), season_number)
            log.info("DOUBAN SEASON: query=%s → score=%d item=%s",
                     query, score, item.get("title", "?"))
            if score > best_score:
                best_score = score
                best_item = item
            if score >= 100 and is_exact:
                break

    if not best_item or best_score < 80:
        log.info("DOUBAN SEASON: show=%s season=%d — no season-specific page found (best_score=%d). Returning None.",
                 show_title, season_number, best_score)
        return None

    log.info("DOUBAN SEASON: FINAL MATCH show=%s season=%s → id=%s title=%s score=%d",
             show_title, season_number,
             best_item.get("id", "?"), best_item.get("title", "?"), best_score)

    result = _parse_rating(best_item)
    if result and result.get("douban_id"):
        detail = _fetch_mobile_detail(result["douban_id"], force_refresh)
        if detail:
            if detail.get("synopsis"):
                result["synopsis"] = detail["synopsis"]
            if detail.get("poster_url"):
                result["poster_url"] = detail["poster_url"]
            if detail.get("air_date"):
                result["air_date"] = detail["air_date"]
            if detail.get("cast_info"):
                result["cast_info"] = detail["cast_info"]
            elif result.get("abstract_2"):
                result["cast_info"] = result["abstract_2"]
    return result


def _fetch_synopsis(douban_id):
    """Fetch plot synopsis from mobile Douban page."""
    if not _douban_available():
        return None
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    ck = f"synopsis:{douban_id}"
    cached = _cache_get(ck)
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        return cached["data"]

    time.sleep(float(cfg.get("douban_request_delay", 0.5)) + random.uniform(0, 0.3))
    url = DOUBAN_MOBILE.format(douban_id)
    synopsis = None
    try:
        req = urllib.request.Request(url, headers=dict(MOBILE_HEADERS, Referer="https://m.douban.com/"))
        with urllib.request.urlopen(req, timeout=15, context=_SSL_CONTEXT) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            m = re.search(r'<section[^>]*class="subject-intro"[^>]*>(.*?)</section>', html, re.DOTALL)
            if m:
                m2 = re.search(r'<p[^>]*>(.*?)</p>', m.group(1), re.DOTALL)
                if m2:
                    synopsis = re.sub(r'<[^>]+>', '', m2.group(1)).strip()
                    synopsis = re.sub(r'\s+', ' ', synopsis)
            if not synopsis:
                m = re.search(r'<meta name="description"[^>]*content="([^"]*)"', html)
                if m:
                    desc = m.group(1)
                    si = desc.find('简介：')
                    if si >= 0:
                        synopsis = desc[si+3:].strip()
    except Exception:
        pass
    _cache_set(ck, {"_cached_at": time.time(), "data": synopsis})
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
