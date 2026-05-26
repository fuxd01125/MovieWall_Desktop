"""SQLite database backend — single source of truth for all data."""
import json
import sqlite3
import time

from moviewall.config import APP_DIR
from moviewall.log import log

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
    episode_count  INTEGER DEFAULT 0,
    UNIQUE(show_id, season_number)
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
    thumb           TEXT,
    UNIQUE(show_id, season_id, episode_number)
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
        progress_seconds REAL DEFAULT 0,
        duration_seconds REAL DEFAULT 0,
        watched_pct     REAL DEFAULT 0,
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
CREATE INDEX IF NOT EXISTS idx_media_path    ON media(path);
CREATE INDEX IF NOT EXISTS idx_media_folder  ON media(folder);
CREATE INDEX IF NOT EXISTS idx_episodes_path ON episodes(path);

-- Scanner state tracking
CREATE TABLE IF NOT EXISTS metadata_tracker (
    key   TEXT PRIMARY KEY,
    value TEXT
);

"""

# ── Connection helpers ──────────────────────────────────────────────

def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA cache_size=-8000")
    return conn


def _migrate_schema_v2():
    """Add UNIQUE constraints and indexes to existing databases.
    Rebuilds seasons and episodes tables with UNIQUE constraints.
    Safe to run multiple times.
    """
    conn = get_conn()
    try:
        row = conn.execute("SELECT value FROM metadata_tracker WHERE key='schema_version'").fetchone()
        if row and row["value"] == "2":
            return
        conn.execute("PRAGMA foreign_keys=OFF")
        # Rebuild seasons with UNIQUE(show_id, season_number)
        conn.execute("""
            CREATE TABLE seasons_v2 (
                id             TEXT PRIMARY KEY,
                show_id        TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                season_number  INTEGER NOT NULL,
                title          TEXT,
                folder         TEXT,
                poster         TEXT,
                episode_count  INTEGER DEFAULT 0,
                UNIQUE(show_id, season_number)
            )
        """)
        conn.execute("INSERT OR IGNORE INTO seasons_v2 SELECT * FROM seasons")
        conn.execute("DROP TABLE IF EXISTS seasons")
        conn.execute("ALTER TABLE seasons_v2 RENAME TO seasons")
        # Rebuild episodes with UNIQUE(show_id, season_id, episode_number)
        conn.execute("""
            CREATE TABLE episodes_v2 (
                id              TEXT PRIMARY KEY,
                show_id         TEXT NOT NULL REFERENCES media(id) ON DELETE CASCADE,
                season_id       TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                season_number   INTEGER NOT NULL,
                episode_number  INTEGER,
                title           TEXT,
                filename        TEXT,
                path            TEXT,
                folder          TEXT,
                thumb           TEXT,
                UNIQUE(show_id, season_id, episode_number)
            )
        """)
        conn.execute("INSERT OR IGNORE INTO episodes_v2 SELECT * FROM episodes")
        conn.execute("DROP TABLE IF EXISTS episodes")
        conn.execute("ALTER TABLE episodes_v2 RENAME TO episodes")
        # Add performance indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_path ON media(path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_media_folder ON media(folder)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_path ON episodes(path)")
        conn.execute("INSERT OR REPLACE INTO metadata_tracker (key, value) VALUES ('schema_version', '2')")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            conn.execute("PRAGMA foreign_keys=ON")
        except Exception:
            pass
        conn.close()


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
        for col in ("progress_seconds", "duration_seconds", "watched_pct"):
            try:
                conn.execute(f"ALTER TABLE history ADD COLUMN {col} REAL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
        # Fix: ensure only one row per media_id (latest played_at), delete old TEXT entries
        try:
            conn.execute("DELETE FROM history WHERE typeof(played_at) = 'text'")
            conn.execute("""
                DELETE FROM history WHERE rowid NOT IN (
                    SELECT MIN(rowid) FROM history
                    GROUP BY media_id
                )
            """)
            conn.commit()
        except sqlite3.OperationalError:
            conn.rollback()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    # Run v2 schema migration (UNIQUE constraints + indexes)
    _migrate_schema_v2()


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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


_DELETE_TABLES = frozenset({"episodes","seasons","metadata_douban_seasons","metadata_tmdb","metadata_douban","media"})

def delete_all_media():
    """Delete only media and metadata — preserve user data (ratings, favorites, history)."""
    conn = get_conn()
    try:
        for t in _DELETE_TABLES:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Batch operations (for scanner performance) ────────────────────

def upsert_media_batch(items):
    """Insert/update multiple media items in a single connection."""
    if not items:
        return
    conn = get_conn()
    try:
        now = time.time()
        for item in items:
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
                now, now,
            ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_season_batch(season_list):
    """Insert/update multiple seasons in a single connection."""
    if not season_list:
        return
    conn = get_conn()
    try:
        for s in season_list:
            conn.execute("""
                INSERT INTO seasons (id,show_id,season_number,title,folder,poster,episode_count)
                VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, folder=excluded.folder, poster=excluded.poster,
                    episode_count=excluded.episode_count
            """, (
                s["id"], s.get("show_id"), s.get("season_number"), s.get("title"),
                s.get("folder"), s.get("poster"), s.get("episode_count", 0)
            ))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_episode_batch(episode_list):
    """Insert/update multiple episodes in a single connection."""
    if not episode_list:
        return
    conn = get_conn()
    try:
        for ep in episode_list:
            conn.execute("""
                INSERT INTO episodes (id,show_id,season_id,season_number,episode_number,title,filename,path,folder,thumb)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title, filename=excluded.filename, path=excluded.path,
                    folder=excluded.folder, thumb=excluded.thumb
            """, (
                ep["id"], ep.get("show_id"), ep.get("season_id"),
                ep.get("season_number"), ep.get("episode_number"),
                ep.get("title"), ep.get("filename"), ep.get("path"),
                ep.get("folder"), ep.get("thumb")
            ))
        conn.commit()
    except Exception:
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
                season_data=excluded.season_data,
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
        # Increment metadata version for freshness tracking
        conn.execute("""
            INSERT INTO metadata_tracker (key, value) VALUES ('metadata_version', 
                COALESCE((SELECT value FROM metadata_tracker WHERE key='metadata_version'), '0'))
            ON CONFLICT(key) DO UPDATE SET
                value = CAST(CAST(COALESCE(metadata_tracker.value, '0') AS INTEGER) + 1 AS TEXT)
        """)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_tmdb_meta(media_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM metadata_tmdb WHERE media_id=?", (media_id,)).fetchone()
    except Exception:
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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_douban_meta(media_id):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM metadata_douban WHERE media_id=?", (media_id,)).fetchone()
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_rating(media_id):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM ratings WHERE media_id=?", (media_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _normalize_played_at(val):
    """Convert played_at to a float (Unix seconds), regardless of storage type."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        # ISO string from old frontend bug
        try:
            return time.mktime(time.strptime(val[:19], "%Y-%m-%dT%H:%M:%S"))
        except (ValueError, OverflowError):
            pass
        # Numeric string
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    log.warning("HISTORY: unparseable played_at %r (%s)", val, type(val).__name__)
    return 0.0


def load_all_history():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM history").fetchall()
    except Exception:
        raise
    finally:
        conn.close()
    # Sort in Python to handle mixed TEXT/REAL played_at correctly
    row_dicts = [dict(r) for r in rows]
    row_dicts.sort(key=lambda r: _normalize_played_at(r.get("played_at")), reverse=True)
    # Per-media dedup: keep latest entry per media_id
    result = {}
    for d in row_dicts:
        mid = d.get("media_id")
        if mid and mid not in result:
            entry = dict(d)
            result[mid] = entry
    # Also return all entries sorted by played_at for future use
    # (frontend uses result[media_id] for continue-watching lookup)
    return result


def save_history(entry):
    conn = get_conn()
    try:
        mid = entry.get("media_id")
        eid = entry.get("episode_id")
        now = entry.get("played_at") or time.time()
        # Only delete old entry for this specific episode (not all episodes in show)
        # This allows per-episode progress tracking
        conn.execute("DELETE FROM history WHERE episode_id=?", (eid,))
        conn.execute("""
            INSERT INTO history (media_id,episode_id,path,title,show_title,season_number,episode_number,label,short_label,played_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (
            mid, eid, entry.get("path"),
            entry.get("title"), entry.get("show_title"),
            entry.get("season_number"), entry.get("episode_number"),
            entry.get("label"), entry.get("short_label"),
            now,
        ))
        conn.commit()
        log.info(
            "HISTORY SAVE: media_id=%s episode_id=%s label=%s played_at=%s",
            mid, eid, entry.get("label"), now,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_history_progress(media_id, episode_id, progress_seconds, duration_seconds=0, path=""):
    """Update playback progress on the history row for this episode.
    Each episode has its own history row for per-episode progress tracking.
    """
    conn = get_conn()
    try:
        watched_pct = (progress_seconds / duration_seconds * 100) if duration_seconds > 0 else 0
        # Update by episode_id since each episode now has its own row
        conn.execute("""
            UPDATE history SET progress_seconds=?, duration_seconds=?, watched_pct=?
            WHERE episode_id=?
        """, (progress_seconds, duration_seconds, watched_pct, episode_id))
        conn.commit()
        log.debug(
            "HISTORY PROGRESS: episode_id=%s progress=%.0fs/%.0fs (%.0f%%)",
            episode_id, progress_seconds, duration_seconds, watched_pct,
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def cleanup_old_history(max_records=500):
    """Remove old history entries beyond max_records, keeping most recent."""
    conn = get_conn()
    try:
        conn.execute("""
            DELETE FROM history WHERE (media_id, played_at) NOT IN (
                SELECT media_id, played_at FROM history
                ORDER BY played_at DESC LIMIT ?
            )
        """, (max_records,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def load_all_favorites():
    conn = get_conn()
    try:
        rows = conn.execute("SELECT media_id FROM favorites").fetchall()
    except Exception:
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
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Batch metadata loaders ─────────────────────────────────────────

def _load_all_tmdb_meta():
    """Load ALL TMDB metadata in one query. Returns dict[media_id → data]."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM metadata_tmdb").fetchall()
    except Exception:
        raise
    finally:
        conn.close()
    result = {}
    for r in rows:
        mid = r["media_id"]
        d = {}
        if r["genres"]:
            try:
                d["genres"] = json.loads(r["genres"])
            except (json.JSONDecodeError, TypeError):
                d["genres"] = []
        if r["season_data"]:
            try:
                d["_season_data"] = json.loads(r["season_data"])
            except (json.JSONDecodeError, TypeError):
                d["_season_data"] = {}
        for k in ("tmdb_id","title","original_title","overview","rating","date","poster_url","backdrop_url","fetched_at"):
            if r[k] is not None:
                d[k] = r[k]
        result[mid] = d
    return result


def _load_all_douban_meta():
    """Load ALL Douban metadata in one query. Returns dict[media_id → data]."""
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM metadata_douban").fetchall()
    except Exception:
        raise
    finally:
        conn.close()
    result = {}
    for r in rows:
        mid = r["media_id"]
        d = {}
        for k in ("douban_id","rating","star_count","rating_count","abstract","abstract_2","synopsis","fetched_at"):
            if r[k] is not None:
                d[k] = r[k]
        result[mid] = d
    return result


def _load_all_shows():
    """Load ALL seasons + episodes in 2 queries. Returns dict[show_id → seasons]."""
    conn = get_conn()
    try:
        season_rows = conn.execute(
            "SELECT * FROM seasons ORDER BY season_number"
        ).fetchall()
        episode_rows = conn.execute(
            "SELECT * FROM episodes ORDER BY season_number, episode_number"
        ).fetchall()
    except Exception:
        raise
    finally:
        conn.close()

    eps_by_season = {}
    for ep in episode_rows:
        eps_by_season.setdefault(ep["season_id"], []).append(dict(ep))

    shows = {}
    for s in season_rows:
        sd = dict(s)
        sd["episodes"] = eps_by_season.get(s["id"], [])
        shows.setdefault(s["show_id"], []).append(sd)
    return shows


def _load_all_douban_season_meta():
    """Load ALL douban season metadata in one query. Returns dict[show_id → {sn → data}]."""
    conn = get_conn()
    try:
        rows = conn.execute(
            """SELECT show_id,season_number,rating,star_count,rating_count,
                      douban_id,synopsis,poster_url,cast_info,air_date
               FROM metadata_douban_seasons"""
        ).fetchall()
    except Exception:
        raise
    finally:
        conn.close()
    result = {}
    for r in rows:
        sid = r["show_id"]
        result.setdefault(sid, {})[str(r["season_number"])] = {
            "rating": r["rating"], "star_count": r["star_count"],
            "rating_count": r["rating_count"], "douban_id": r["douban_id"],
            "synopsis": r["synopsis"], "poster_url": r["poster_url"],
            "cast_info": r["cast_info"], "air_date": r["air_date"],
        }
    return result


# ── Library query (for API) ─────────────────────────────────────────

def build_library_dict():
    """Return the full library as a dict, compatible with the old JSON API."""
    conn = get_conn()
    try:
        media_rows = conn.execute("SELECT * FROM media ORDER BY title COLLATE NOCASE").fetchall()
    except Exception:
        raise
    finally:
        conn.close()

    # Batch-load all metadata in a few queries
    all_tmdb = _load_all_tmdb_meta()
    all_douban = _load_all_douban_meta()
    all_shows = _load_all_shows()
    all_ds = _load_all_douban_season_meta()

    items = []
    for m in media_rows:
        item = dict(m)
        item["type"] = item.pop("media_type")
        mid = item["id"]

        meta = {}
        tmdb = all_tmdb.get(mid)
        douban = all_douban.get(mid)
        if tmdb:
            meta["tmdb"] = tmdb
        if douban:
            meta["douban"] = douban
            # API-layer fallback: if TMDB overview is empty, use Douban synopsis
            # This avoids writing Douban data into TMDB DB fields (metadata pollution fix)
            if tmdb and not tmdb.get("overview", "").strip() and douban.get("synopsis", "").strip():
                meta["tmdb"] = dict(tmdb)
                meta["tmdb"]["overview"] = douban["synopsis"]
        item["metadata"] = meta

        if item["type"] == "show":
            seasons_data = all_shows.get(mid, [])
            ds = all_ds.get(mid, {})
            # Merge per-season TMDB and Douban metadata into each season object
            season_tmdb = tmdb.get("_season_data", {}) if tmdb else {}
            for s in seasons_data:
                ssn = str(s.get("season_number", ""))
                # Douban per-season metadata
                s_meta = ds.get(ssn, {})
                if s_meta:
                    s["douban"] = s_meta
                # TMDB per-season overview (overrides show-level overview for season)
                st = season_tmdb.get(ssn, {})
                if st:
                    s["tmdb"] = st
            item["seasons"] = seasons_data
            if ds:
                item["_season_meta"] = ds

        items.append(item)

    # Freshness tracking
    conn3 = get_conn()
    try:
        version_row = conn3.execute("SELECT value FROM metadata_tracker WHERE key='metadata_version'").fetchone()
        metadata_version = version_row["value"] if version_row else "0"
    except Exception:
        metadata_version = "0"
    finally:
        conn3.close()

    stats = {
        "movies": sum(1 for i in items if i["type"] == "movie"),
        "shows": sum(1 for i in items if i["type"] == "show"),
        "episodes": sum(i.get("episode_count", 0) for i in items if i["type"] == "show"),
        "metadata_version": metadata_version,
    }
    return {"items": items, "stats": stats}
