"""SQLite database backend — single source of truth for all data."""
import json
import sqlite3
import time

from moviewall.config import APP_DIR

DB_PATH = APP_DIR / "library.db"

# ── Schema ──────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id            TEXT PRIMARY KEY,
    media_type    TEXT NOT NULL,       -- 'movie' | 'show'
    title         TEXT NOT NULL,
    display_title TEXT,
    year          TEXT,
    category_key  TEXT,
    category_name TEXT,
    folder        TEXT,
    path          TEXT,
    filename      TEXT,
    poster        TEXT,
    thumb         TEXT,
    season_count  INTEGER DEFAULT 0,
    episode_count INTEGER DEFAULT 0,
    created_at    REAL,
    updated_at    REAL
);

CREATE TABLE IF NOT EXISTS seasons (
    id             TEXT PRIMARY KEY,
    show_id        TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    season_number  INTEGER NOT NULL,
    title          TEXT,
    folder         TEXT,
    poster         TEXT,
    episode_count  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS episodes (
    id              TEXT PRIMARY KEY,
    show_id         TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    season_id       TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
    season_number   INTEGER NOT NULL,
    episode_number  INTEGER,
    title           TEXT,
    filename        TEXT,
    path            TEXT,
    folder          TEXT,
    thumb           TEXT
);

-- TMDB metadata — fully separate from core & douban
CREATE TABLE IF NOT EXISTS metadata_tmdb (
    media_id      TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
    tmdb_id       INTEGER,
    title         TEXT,
    original_title TEXT,
    overview      TEXT,
    rating        REAL,
    date          TEXT,
    genres        TEXT,       -- JSON array
    poster_url    TEXT,
    backdrop_url  TEXT,
    season_data   TEXT,       -- JSON: { "1": {"rating":8.5, "air_date":"...", "overview":"..."}, ... }
    raw           TEXT,       -- full TMDB response (JSON)
    fetched_at    REAL
);

-- Douban metadata — fully separate from core & tmdb
CREATE TABLE IF NOT EXISTS metadata_douban (
    media_id      TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
    douban_id     TEXT,
    rating        REAL,
    star_count    REAL,
    rating_count  INTEGER,
    abstract      TEXT,
    abstract_2    TEXT,
    synopsis      TEXT,
    raw           TEXT,       -- full response (JSON)
    fetched_at    REAL
);

-- Per-season Douban ratings (separate from show-level)
CREATE TABLE IF NOT EXISTS metadata_douban_seasons (
    season_id     TEXT PRIMARY KEY REFERENCES seasons(id) ON DELETE CASCADE,
    show_id       TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
    season_number INTEGER NOT NULL,
    douban_id     TEXT,
    rating        REAL,
    star_count    REAL,
    rating_count  INTEGER,
    synopsis      TEXT,
    poster_url    TEXT,
    cast_info     TEXT,
    air_date      TEXT,
    fetched_at    REAL
);

-- User data
CREATE TABLE IF NOT EXISTS ratings (
    media_id  TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
    score     REAL NOT NULL,
    rated_at  REAL
);

CREATE TABLE IF NOT EXISTS history (
    media_id        TEXT,
    episode_id      TEXT,
    path            TEXT,
    title           TEXT,
    show_title      TEXT,
    season_number   INTEGER,
    episode_number  INTEGER,
    label           TEXT,
    short_label     TEXT,
    played_at       REAL,
    PRIMARY KEY (media_id, played_at)
);

CREATE TABLE IF NOT EXISTS favorites (
    media_id     TEXT PRIMARY KEY REFERENCES media(id) ON DELETE CASCADE,
    favorited_at REAL
);

CREATE INDEX IF NOT EXISTS idx_seasons_show   ON seasons(show_id);
CREATE INDEX IF NOT EXISTS idx_episodes_show  ON episodes(show_id);
CREATE INDEX IF NOT EXISTS idx_episodes_season ON episodes(season_id);
CREATE INDEX IF NOT EXISTS idx_history_media  ON history(media_id);

"""

# ── Connection helpers ──────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # Migrate: add columns that might be missing from older DB
        for col in ("rating_count", "synopsis", "poster_url", "cast_info", "air_date"):
            try:
                conn.execute(f"ALTER TABLE metadata_douban_seasons ADD COLUMN {col} TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def scrub_row(row):
    """Convert sqlite3.Row → plain dict."""
    if row is None:
        return None
    return dict(row)


def scrub_rows(rows):
    return [dict(r) for r in rows]


# ── Media CRUD ──────────────────────────────────────────────────────

def upsert_media(item):
    conn = get_conn()
    try:
        now = time.time()
        conn.execute("""
            INSERT INTO media (id,media_type,title,display_title,year,category_key,category_name,
                               folder,path,filename,poster,thumb,season_count,episode_count,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, display_title=excluded.display_title, year=excluded.year,
                category_key=excluded.category_key, category_name=excluded.category_name,
                folder=excluded.folder, path=excluded.path, filename=excluded.filename,
                poster=excluded.poster, thumb=excluded.thumb,
                season_count=excluded.season_count, episode_count=excluded.episode_count,
                updated_at=excluded.updated_at
        """, (
            item["id"], item.get("type"), item.get("title"), item.get("display_title"),
            item.get("year"), item.get("category_key"), item.get("category_name"),
            item.get("folder"), item.get("path"), item.get("filename"),
            item.get("poster"), item.get("thumb"),
            item.get("season_count", 0), item.get("episode_count", 0),
            now,  # created_at
            now,  # updated_at
        ))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_season(show_id, season):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO seasons (id,show_id,season_number,title,folder,poster,episode_count)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, folder=excluded.folder, poster=excluded.poster,
                episode_count=excluded.episode_count
        """, (
            season["id"], show_id, season.get("season_number"), season.get("title"),
            season.get("folder"), season.get("poster"), season.get("episode_count", 0)
        ))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_episode(show_id, season_id, ep):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO episodes (id,show_id,season_id,season_number,episode_number,title,filename,path,folder,thumb)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, filename=excluded.filename, path=excluded.path,
                folder=excluded.folder, thumb=excluded.thumb
        """, (
            ep["id"], show_id, season_id, ep.get("season_number"), ep.get("episode_number"),
            ep.get("title"), ep.get("filename"), ep.get("path"), ep.get("folder"), ep.get("thumb")
        ))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_media(media_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM episodes WHERE show_id=?", (media_id,))
        conn.execute("DELETE FROM seasons WHERE show_id=?", (media_id,))
        conn.execute("DELETE FROM metadata_tmdb WHERE media_id=?", (media_id,))
        conn.execute("DELETE FROM metadata_douban WHERE media_id=?", (media_id,))
        conn.execute("DELETE FROM metadata_douban_seasons WHERE show_id=?", (media_id,))
        conn.execute("DELETE FROM history WHERE media_id=?", (media_id,))
        conn.execute("DELETE FROM favorites WHERE media_id=?", (media_id,))
        conn.execute("DELETE FROM ratings WHERE media_id=?", (media_id,))
        conn.execute("DELETE FROM media WHERE id=?", (media_id,))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_all_media():
    """Delete only media and metadata — preserve user data (ratings, favorites, history)."""
    conn = get_conn()
    try:
        tables = ("episodes","seasons","metadata_douban_seasons","metadata_tmdb","metadata_douban","media")
        for t in tables:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Metadata storage (separate tables) ──────────────────────────────

def save_tmdb_meta(media_id, data):
    conn = get_conn()
    try:
        season_data = data.get("_season_data")
        conn.execute("""
            INSERT INTO metadata_tmdb (media_id,tmdb_id,title,original_title,overview,rating,date,
                                       genres,poster_url,backdrop_url,season_data,raw,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(media_id) DO UPDATE SET
                tmdb_id=excluded.tmdb_id, title=excluded.title, original_title=excluded.original_title,
                overview=excluded.overview, rating=excluded.rating, date=excluded.date,
                genres=excluded.genres, poster_url=excluded.poster_url, backdrop_url=excluded.backdrop_url,
                season_data=COALESCE(NULLIF(excluded.season_data,''),metadata_tmdb.season_data),
                raw=excluded.raw, fetched_at=excluded.fetched_at
        """, (
            media_id,
            data.get("tmdb_id"),
            data.get("title"),
            data.get("original_title"),
            data.get("overview"),
            data.get("rating"),
            data.get("date"),
            json.dumps(data.get("genres", []), ensure_ascii=False),
            data.get("poster_url"),
            data.get("backdrop_url"),
            json.dumps(season_data, ensure_ascii=False) if season_data else None,
            json.dumps(data, ensure_ascii=False),
            time.time(),
        ))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_tmdb_meta(media_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM metadata_tmdb WHERE media_id=?", (media_id,)).fetchone()
    except:
        raise
    finally:
        conn.close()
    if row is None:
        return {}
    r = dict(row)
    data = {}
    if r.get("genres"):
        try:
            data["genres"] = json.loads(r["genres"])
        except (json.JSONDecodeError, TypeError):
            data["genres"] = []
    if r.get("season_data"):
        try:
            data["_season_data"] = json.loads(r["season_data"])
        except (json.JSONDecodeError, TypeError):
            data["_season_data"] = {}
    for k in ("tmdb_id","title","original_title","overview","rating","date","poster_url","backdrop_url","fetched_at"):
        if r.get(k) is not None:
            data[k] = r[k]
    return data


def save_douban_meta(media_id, data):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO metadata_douban (media_id,douban_id,rating,star_count,rating_count,abstract,abstract_2,synopsis,raw,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(media_id) DO UPDATE SET
                douban_id=COALESCE(NULLIF(excluded.douban_id,''), metadata_douban.douban_id),
                rating=COALESCE(excluded.rating, metadata_douban.rating),
                star_count=COALESCE(excluded.star_count, metadata_douban.star_count),
                rating_count=COALESCE(excluded.rating_count, metadata_douban.rating_count),
                abstract=COALESCE(NULLIF(excluded.abstract,''), metadata_douban.abstract),
                abstract_2=COALESCE(NULLIF(excluded.abstract_2,''), metadata_douban.abstract_2),
                synopsis=COALESCE(NULLIF(excluded.synopsis,''), metadata_douban.synopsis),
                raw=excluded.raw, fetched_at=excluded.fetched_at
        """, (
            media_id,
            data.get("douban_id"),
            data.get("rating"),
            data.get("star_count"),
            data.get("rating_count"),
            data.get("abstract"),
            data.get("abstract_2"),
            data.get("synopsis"),
            json.dumps(data, ensure_ascii=False),
            time.time(),
        ))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_douban_meta(media_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM metadata_douban WHERE media_id=?", (media_id,)).fetchone()
    except:
        raise
    finally:
        conn.close()
    if row is None:
        return {}
    r = dict(row)
    out = {}
    for k in ("douban_id","rating","star_count","rating_count","abstract","abstract_2","synopsis","fetched_at"):
        if r.get(k) is not None:
            out[k] = r[k]
    return out


def save_douban_season_meta(season_id, show_id, season_number, data):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO metadata_douban_seasons (season_id,show_id,season_number,douban_id,rating,star_count,rating_count,synopsis,poster_url,cast_info,air_date,fetched_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(season_id) DO UPDATE SET
                douban_id=excluded.douban_id, rating=excluded.rating, star_count=excluded.star_count,
                rating_count=excluded.rating_count, synopsis=excluded.synopsis, poster_url=excluded.poster_url,
                cast_info=excluded.cast_info, air_date=excluded.air_date, fetched_at=excluded.fetched_at
        """, (
            season_id, show_id, season_number,
            data.get("douban_id"), data.get("rating"), data.get("star_count"),
            data.get("rating_count"), data.get("synopsis"), data.get("poster_url"),
            data.get("cast_info"), data.get("air_date"),
            time.time(),
        ))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_douban_season_meta(show_id):
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT season_number,rating,star_count,rating_count,douban_id,synopsis,poster_url,cast_info,air_date
               FROM metadata_douban_seasons WHERE show_id=?""",
            (show_id,)
        ).fetchall()
    except:
        raise
    finally:
        conn.close()
    return {str(r["season_number"]): {
        "rating": r["rating"], "star_count": r["star_count"],
        "rating_count": r["rating_count"], "douban_id": r["douban_id"],
        "synopsis": r["synopsis"], "poster_url": r["poster_url"],
        "cast_info": r["cast_info"], "air_date": r["air_date"],
    } for r in rows}


# ── User data ───────────────────────────────────────────────────────

def load_all_ratings():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT media_id,score,rated_at FROM ratings").fetchall()
    except:
        raise
    finally:
        conn.close()
    return {r["media_id"]: {"score": r["score"], "rated_at": r["rated_at"]} for r in rows}


def save_rating(media_id, score):
    conn = get_conn()
    try:
        conn.execute("INSERT OR REPLACE INTO ratings (media_id,score,rated_at) VALUES (?,?,?)",
                     (media_id, score, time.time()))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_rating(media_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ratings WHERE media_id=?", (media_id,))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_all_history():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM history ORDER BY played_at DESC").fetchall()
    except:
        raise
    finally:
        conn.close()
    result = {}
    for r in rows:
        d = dict(r)
        mid = d.pop("media_id")
        if mid not in result:
            result[mid] = d
    return result


def save_history(entry):
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO history (media_id,episode_id,path,title,show_title,season_number,episode_number,label,short_label,played_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            entry.get("media_id"), entry.get("episode_id"), entry.get("path"),
            entry.get("title"), entry.get("show_title"),
            entry.get("season_number"), entry.get("episode_number"),
            entry.get("label"), entry.get("short_label"),
            entry.get("played_at") or time.time(),
        ))
        conn.commit()
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_all_favorites():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT media_id FROM favorites").fetchall()
    except:
        raise
    finally:
        conn.close()
    return [r["media_id"] for r in rows]


def toggle_favorite(media_id):
    conn = get_conn()
    try:
        existing = conn.execute("SELECT media_id FROM favorites WHERE media_id=?", (media_id,)).fetchone()
        if existing:
            conn.execute("DELETE FROM favorites WHERE media_id=?", (media_id,))
            conn.commit()
            return "removed"
        else:
            conn.execute("INSERT OR IGNORE INTO favorites (media_id,favorited_at) VALUES (?,?)",
                         (media_id, time.time()))
            conn.commit()
            return "added"
    except:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Library query (for API) ─────────────────────────────────────────

def build_library_dict():
    """Return the full library as a dict, compatible with the old JSON API."""
    conn = get_conn()
    try:
        media_rows = conn.execute("SELECT * FROM media ORDER BY title COLLATE NOCASE").fetchall()
    except:
        raise
    finally:
        conn.close()

    items = []
    for m in media_rows:
        item = dict(m)
        item["type"] = item.pop("media_type")
        # Attach metadata
        tmdb = load_tmdb_meta(item["id"])
        douban = load_douban_meta(item["id"])
        meta = {}
        if tmdb:
            meta["tmdb"] = tmdb
        if douban:
            meta["douban"] = douban
        item["metadata"] = meta

        # Attach seasons + episodes for shows
        if item["type"] == "show":
            conn2 = get_conn()
            try:
                seasons = scrub_rows(conn2.execute(
                    "SELECT * FROM seasons WHERE show_id=? ORDER BY season_number", (item["id"],)
                ).fetchall())
                for s in seasons:
                    s["episodes"] = scrub_rows(conn2.execute(
                        "SELECT * FROM episodes WHERE season_id=? ORDER BY episode_number", (s["id"],)
                    ).fetchall())
            except:
                raise
            finally:
                conn2.close()
            item["seasons"] = seasons
            # Attach per-season douban ratings
            ds = load_douban_season_meta(item["id"])
            if ds:
                item["_season_meta"] = ds

        items.append(item)

    stats = {
        "movies": sum(1 for i in items if i["type"] == "movie"),
        "shows": sum(1 for i in items if i["type"] == "show"),
        "episodes": sum(i.get("episode_count", 0) for i in items if i["type"] == "show"),
    }
    return {"items": items, "stats": stats}
