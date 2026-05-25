"""Douban scraper — search, rating, synopsis, per-season support."""
import http.cookiejar
import json
import random
import re
import time
import urllib.parse
import urllib.request

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE, cache_lock

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
    delay = float(cfg.get("douban_request_delay", 0.5)) + random.uniform(0, 0.3)
    time.sleep(delay)
    if opener is None:
        opener = _get_opener()
    h = dict(HEADERS, Referer="https://movie.douban.com/")
    try:
        with opener.open(urllib.request.Request(url, headers=h), timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
            if "登录重定向" in html or "检测到异常" in html:
                _douban_blocked_log()
                return None
            return html
    except urllib.error.HTTPError as e:
        if e.code == 403:
            _douban_blocked_log()
        return None
    except Exception:
        return None


_blocked_logged = False

def _douban_blocked_log():
    global _blocked_logged
    if not _blocked_logged:
        _blocked_logged = True
        print("[豆瓣] 请求被屏蔽（HTTP 403），豆瓣数据不可用。TMDB 数据不受影响。")


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


def _pick_best(items, year, season_number=None):
    """Pick best matching item from douban search results.
       When season_number is set, only returns items that explicitly 
       mention that season — never falls back to the main show page.
    """
    valid = [i for i in items if i.get("tpl_name") in ("search_subject", None, "")]
    if not valid:
        return None
    # 1) year match + season mention (if searching for a season)
    for item in valid:
        iy = item.get("year", "") or _year_from_title(item.get("title", ""))
        if year and iy and str(year) in str(iy):
            if season_number is None or _season_match_score(item.get("title", ""), season_number) > 0:
                return item
    # 2) if looking for a specific season, pick the best season-match item
    if season_number is not None:
        scored = [(item, _season_match_score(item.get("title", ""), season_number)) for item in valid]
        scored.sort(key=lambda x: x[1], reverse=True)
        if scored[0][1] >= 80:
            return scored[0][0]
        # No season-specific result → return None rather than wrong data
        return None
    # 3) (show-level search) prefer item with a rating
    for item in valid:
        if item.get("rating", {}).get("value"):
            return item
    return valid[0]


def _search(title, year, season_number=None):
    """Search douban, return best matching item dict or None.
       TV category only — no all-categories fallback (avoids wrong results).
    """
    opener = _get_opener()
    candidates = [title]
    stripped = re.sub(r'[：:（(][^)）]*[)）]', '', title).strip()
    if stripped and stripped != title:
        candidates.append(stripped)

    for t in candidates:
        if not t:
            continue
        params = {"search_text": t, "cat": "1002"}
        url = DOUBAN_SEARCH + "?" + urllib.parse.urlencode(params)
        html = _request(url, opener)
        if not html:
            continue
        items = _parse_items(html)
        if not items:
            continue
        best = _pick_best(items, year, season_number)
        if best:
            return best
    return None


def _search_raw(title):
    """Search douban and return ALL valid items (unfiltered). Used for season matching."""
    opener = _get_opener()
    params = {"search_text": title, "cat": "1002"}
    url = DOUBAN_SEARCH + "?" + urllib.parse.urlencode(params)
    html = _request(url, opener)
    if not html:
        return []
    items = _parse_items(html)
    if not items:
        return []
    return [i for i in items if i.get("tpl_name") in ("search_subject", None, "")]


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

def fetch_douban_meta(title, year):
    """Fetch Douban rating + abstract for a movie/show. Returns dict or None."""
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    key = f"douban:{urllib.parse.quote(title)}:{year or ''}"
    cached = _cache_get(key)
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        result = cached["data"]
    else:
        item = _search(title, year)
        result = _parse_rating(item) if item else None
        _cache_set(key, {"_cached_at": time.time(), "data": result})

    if result and result.get("douban_id") and not result.get("synopsis"):
        syn = _fetch_synopsis(result["douban_id"])
        if syn:
            result["synopsis"] = syn
    return result


def fetch_douban_by_id(douban_id):
    """Fetch Douban data for a known ID."""
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


def _fetch_mobile_detail(douban_id):
    """Fetch synopsis + poster + other details from mobile page."""
    cfg = load_config()
    ttl = int(cfg.get("metadata_cache_days", 30)) * 86400
    ck = f"mobile:{douban_id}"
    cached = _cache_get(ck)
    if cached and cached.get("data") is not None and time.time() - cached.get("_cached_at", 0) < ttl:
        return cached["data"]

    time.sleep(float(cfg.get("douban_request_delay", 0.5)) + random.uniform(0, 0.3))
    url = DOUBAN_MOBILE.format(douban_id)
    result = {}
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=dict(MOBILE_HEADERS, Referer="https://m.douban.com/")),
            timeout=15,
        ) as resp:
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


def _cn_digits(n):
    mapping = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九"}
    return mapping.get(n, str(n))


def fetch_douban_by_season(show_title, show_year, season_number, original_title="", fallback_douban_id=None):
    """Search Douban for a specific season of a show.
       Strategy:
       1. Exact season title search (e.g. "汉尼拔 第二季")
       2. Show title broad search — find season in ALL results
       3. If no season-specific page found, use show-level douban_id as fallback
    """
    cn = _cn_digits(season_number)
    best_item = None
    best_score = -1

    # Step 1: exact season title
    for kw in (f"{show_title} 第{cn}季",):
        item = _search(kw, show_year, season_number)
        if item:
            score = _season_match_score(item.get("title", ""), season_number)
            if score >= 100:
                best_item, best_score = item, score

    # Step 2: broad show-title search, scan ALL results for season match
    if not best_item:
        search_titles = [show_title]
        if original_title and original_title != show_title:
            search_titles.append(original_title)
        for st in search_titles:
            all_items = _search_raw(st)
            for item in all_items:
                score = _season_match_score(item.get("title", ""), season_number)
                if score > best_score:
                    best_score = score
                    best_item = item
            if best_score >= 80:
                break

    # Step 3: fallback to show-level douban_id if no season page found
    if (not best_item or best_score <= 0) and fallback_douban_id:
        result = {"douban_id": fallback_douban_id, "rating": None, "star_count": None, "rating_count": None, "abstract": "", "abstract_2": ""}
        detail = _fetch_mobile_detail(fallback_douban_id) or {}
        for field in ("synopsis", "poster_url", "air_date", "cast_info"):
            if detail.get(field):
                result[field] = detail[field]
        if not result.get("synopsis"):
            syn = _fetch_synopsis(fallback_douban_id)
            if syn:
                result["synopsis"] = syn
        return result

    if not best_item or best_score <= 0:
        return None

    result = _parse_rating(best_item)
    if result and result.get("douban_id"):
        detail = _fetch_mobile_detail(result["douban_id"])
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
        with urllib.request.urlopen(
            urllib.request.Request(url, headers=dict(MOBILE_HEADERS, Referer="https://m.douban.com/")),
            timeout=15,
        ) as resp:
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
