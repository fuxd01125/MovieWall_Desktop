import random
import re
import time
import urllib.parse
import urllib.request

from moviewall.config import load_config, read_json, write_json, METADATA_CACHE_FILE

DOUBAN_SEARCH_URL = "https://movie.douban.com/subject_search"
DOUBAN_SUBJECT_URL = "https://movie.douban.com/subject/{}/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5",
    "Referer": "https://movie.douban.com/",
}


def _request(url):
    cfg = load_config()
    delay = float(cfg.get("douban_request_delay", 1.5))
    time.sleep(delay + random.uniform(0, 0.5))
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
            return html
    except Exception:
        return None


def _extract_douban_id(html):
    ids = set()
    for m in re.finditer(r'https://movie\.douban\.com/subject/(\d+)/?', html):
        ids.add(m.group(1))
    return ids


def _match_year(html, target_year):
    if not target_year:
        return True
    for m in re.finditer(r'<span class="pl">(?:上映|首播).*?(\d{4})', html):
        if m.group(1) == target_year:
            return True
    for m in re.finditer(r'<span class="year">\(?(\d{4})\)?</span>', html):
        if m.group(1) == target_year:
            return True
    return False


def search_douban_id(title_cn, title_en, year):
    candidates = [title_cn, title_en] if title_en else [title_cn]
    for t in candidates:
        if not t:
            continue
        params = {"search_text": t, "cat": "1002"}
        url = DOUBAN_SEARCH_URL + "?" + urllib.parse.urlencode(params)
        html = _request(url)
        if not html:
            continue
        ids = _extract_douban_id(html)
        if not ids:
            continue
        if year and len(ids) > 1:
            for _id in ids:
                detail_html = _request(DOUBAN_SUBJECT_URL.format(_id))
                if detail_html and _match_year(detail_html, year):
                    return _id
        return list(ids)[0]
    return None


def fetch_douban_detail(douban_id):
    url = DOUBAN_SUBJECT_URL.format(douban_id)
    html = _request(url)
    if not html:
        return None

    rating = ""
    m = re.search(r'<strong class="ll rating_num"[^>]*>(.*?)</strong>', html)
    if m:
        raw = m.group(1).strip()
        try:
            rating = float(raw) if raw else ""
        except ValueError:
            rating = ""

    rating_count = ""
    m = re.search(r'<span[^>]*>\s*([\d,]+)\s*人评价\s*</span>', html)
    if m:
        rating_count = m.group(1).replace(",", "")

    synopsis = ""
    m = re.search(r'<span[^>]*property="v:summary"[^>]*>(.*?)</span>', html, re.DOTALL)
    if m:
        synopsis = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        synopsis = re.sub(r'\s+', ' ', synopsis)
    if not synopsis:
        m = re.search(r'<div\s+class="indent"[^>]*>\s*"?(.*?)"?\s*</div>', html, re.DOTALL)
        if m:
            synopsis = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            synopsis = re.sub(r'\s+', ' ', synopsis)

    if not rating and not synopsis:
        return None

    result = {"douban_id": douban_id}
    if rating:
        result["rating"] = rating
    if rating_count:
        result["rating_count"] = int(rating_count)
    if synopsis:
        result["synopsis"] = synopsis
    return result


def get_douban_metadata(title_cn, title_en, year, media_type):
    cfg = load_config()
    if not cfg.get("douban_enabled", True):
        return None

    cache = read_json(METADATA_CACHE_FILE, {})
    search_key = f"douban:{urllib.parse.quote(title_cn)}:{year or ''}"
    cached = cache.get(search_key)

    if cached and time.time() - cached.get("_cached_at", 0) < int(cfg.get("metadata_cache_days", 30)) * 86400:
        return cached.get("data")

    douban_id = search_douban_id(title_cn, title_en, year)
    if not douban_id:
        cache[search_key] = {"_cached_at": time.time(), "data": None}
        write_json(METADATA_CACHE_FILE, cache)
        return None

    detail = fetch_douban_detail(douban_id)
    cache[search_key] = {"_cached_at": time.time(), "data": detail}
    write_json(METADATA_CACHE_FILE, cache)
    return detail


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


def get_douban_metadata_by_id(douban_id):
    """Fetch Douban metadata for a manually provided ID, with caching."""
    cache = read_json(METADATA_CACHE_FILE, {})
    cache_key = f"douban_id:{douban_id}"
    cached = cache.get(cache_key)
    cfg = load_config()
    if cached and time.time() - cached.get("_cached_at", 0) < int(cfg.get("metadata_cache_days", 30)) * 86400:
        return cached.get("data")
    detail = fetch_douban_detail(douban_id)
    cache[cache_key] = {"_cached_at": time.time(), "data": detail}
    write_json(METADATA_CACHE_FILE, cache)
    return detail
