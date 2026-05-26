"""Flask routes — API endpoints backed by SQLite database."""
import os
import subprocess
import threading
import time
from pathlib import Path

from flask import abort, jsonify, redirect, render_template, request, send_file

from moviewall.config import load_config, write_json, CONFIG_FILE, load_players, normalize_categories
from moviewall.log import log
from moviewall.database import (
    build_library_dict, load_all_ratings, load_all_history, load_all_favorites,
    save_rating, delete_rating, save_history, toggle_favorite,
    load_tmdb_meta, load_douban_meta, save_douban_meta, save_tmdb_meta,
    get_conn,
)
from moviewall.douban import fetch_douban_by_id, set_douban_id_override
from moviewall.scanner import scan_library
from moviewall.metadata import attach_all_metadata

# ── Helpers ─────────────────────────────────────────────────────────

_scan_progress = {"progress": 0, "message": "", "done": False, "error": ""}
_scan_lock = threading.Lock()


def find_media_by_id(media_id):
    from moviewall.database import scrub_rows
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    except Exception:
        raise
    finally:
        conn.close()
    if row is None:
        return None
    item = dict(row)
    item["type"] = item.pop("media_type")
    meta = {}
    tmdb = load_tmdb_meta(media_id)
    douban = load_douban_meta(media_id)
    if tmdb:
        meta["tmdb"] = tmdb
    if douban:
        meta["douban"] = douban
    item["metadata"] = meta
    if item["type"] == "show":
        conn2 = get_conn()
        try:
            seasons = scrub_rows(conn2.execute(
                "SELECT * FROM seasons WHERE show_id=? ORDER BY season_number", (media_id,)
            ).fetchall())
            for s in seasons:
                s["episodes"] = scrub_rows(conn2.execute(
                    "SELECT * FROM episodes WHERE season_id=? ORDER BY episode_number", (s["id"],)
                ).fetchall())
        except Exception:
            raise
        finally:
            conn2.close()
        item["seasons"] = seasons
    return item


def is_allowed_media_path(path):
    try:
        target = str(Path(path).resolve())
    except Exception:
        return False
    conn = get_conn()
    try:
        media_rows = conn.execute("SELECT path FROM media WHERE path IS NOT NULL").fetchall()
        ep_rows = conn.execute("SELECT path FROM episodes WHERE path IS NOT NULL").fetchall()
        all_rows = list(media_rows) + list(ep_rows)
    except Exception:
        raise
    finally:
        conn.close()
    for r in all_rows:
        try:
            if str(Path(r["path"]).resolve()) == target:
                return True
        except Exception:
            pass
    return False


def is_allowed_folder(folder):
    try:
        target = str(Path(folder).resolve())
    except Exception:
        return False
    conn = get_conn()
    try:
        rows = conn.execute("SELECT folder FROM media WHERE folder IS NOT NULL").fetchall()
    except Exception:
        raise
    finally:
        conn.close()
    for r in rows:
        try:
            if str(Path(r["folder"]).resolve()) == target:
                return True
        except Exception:
            pass
    return False


# ── Route Registration ──────────────────────────────────────────────

def register_routes(app):

    @app.before_request
    def _request_start():
        request._start_time = time.time()

    @app.after_request
    def _request_log(resp):
        elapsed = time.time() - getattr(request, "_start_time", time.time())
        if elapsed > 0.5:
            log.warning("Slow request: %s %s (%.2fs)", request.method, request.path, elapsed)
        elif elapsed > 0.1:
            log.info("Request: %s %s (%.2fs)", request.method, request.path, elapsed)
        return resp

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/library")
    def api_library():
        return jsonify(build_library_dict())

    @app.route("/api/scan", methods=["POST"])
    def api_scan():
        def _run():
            global _scan_progress, _scan_lock
            with _scan_lock:
                _scan_progress = {"progress": 0, "message": "开始扫描...", "done": False, "error": ""}
            try:
                def cb(p, msg):
                    global _scan_progress, _scan_lock
                    with _scan_lock:
                        _scan_progress = {"progress": p, "message": msg, "done": False, "error": ""}
                scan_library(progress_callback=cb)
                with _scan_lock:
                    _scan_progress["done"] = True
            except Exception as e:
                with _scan_lock:
                    _scan_progress = {"progress": 1, "message": str(e), "done": True, "error": str(e)}

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return jsonify({"ok": True, "message": "扫描已启动"})

    @app.route("/api/scan/progress")
    def api_scan_progress():
        with _scan_lock:
            return jsonify(dict(_scan_progress))

    @app.route("/api/update", methods=["POST"])
    def api_update_metadata():
        """Force re-fetch TMDB + Douban metadata for all items with full cache invalidation."""

        def _clear_item_cache(item_id, item_title):
            """Clear cached TMDB search results for this item from metadata_cache.json."""
            from moviewall.metadata import clear_tmdb_cache
            clear_tmdb_cache(item_id, item_title)
            log.info("CLEAR CACHE: item=%s title=%s", item_id, item_title)

        def _run():
            global _scan_progress, _scan_lock
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with _scan_lock:
                _scan_progress = {"progress": 0, "message": "开始更新元数据...", "done": False, "error": ""}
            lib = build_library_dict()
            items = lib.get("items", [])
            total = len(items)
            try:
                if total > 0:
                    max_workers = min(5, total)
                    with ThreadPoolExecutor(max_workers=max_workers) as pool:
                        # First, clear all cache entries
                        log.info("UPDATE: clearing metadata cache for %d items", total)
                        for item in items:
                            _clear_item_cache(item["id"], item.get("title", ""))
                        # Then re-fetch metadata with force_refresh
                        futures = {pool.submit(attach_all_metadata, item, True): item for item in items}
                        done = 0
                        for future in as_completed(futures):
                            done += 1
                            item = futures[future]
                            with _scan_lock:
                                _scan_progress = {"progress": done / total if total else 1,
                                                  "message": f"更新: {item.get('display_title') or item.get('title')}",
                                                  "done": False, "error": ""}
                            try:
                                future.result()
                            except Exception:
                                pass
                with _scan_lock:
                    _scan_progress["done"] = True
            except Exception as e:
                with _scan_lock:
                    _scan_progress = {"progress": 1, "message": str(e), "done": True, "error": str(e)}

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return jsonify({"ok": True, "message": "更新已启动"})

    @app.route("/api/artwork/<media_id>/<kind>")
    def api_artwork(media_id, kind):
        item = find_media_by_id(media_id)
        art_path = None
        if item:
            art_path = item.get(kind)
        if not art_path:
            # Fallback: query seasons/episodes directly (media_id may be a season or episode ID)
            conn2 = get_conn()
            try:
                if kind == "poster":
                    row = conn2.execute("SELECT poster FROM seasons WHERE id=?", (media_id,)).fetchone()
                    if row:
                        art_path = row["poster"]
                elif kind == "thumb":
                    row = conn2.execute("SELECT thumb FROM episodes WHERE id=?", (media_id,)).fetchone()
                    if row:
                        art_path = row["thumb"]
            except Exception:
                raise
            finally:
                conn2.close()
        if not art_path:
            abort(404)
        # If artwork path is a remote URL, redirect instead of local file serving
        if isinstance(art_path, str) and art_path.startswith("http"):
            return redirect(art_path)
        p = Path(art_path)
        if not p.exists() or not p.is_file():
            abort(404)
        return send_file(str(p))

    @app.route("/api/play", methods=["POST"])
    def api_play():
        data = request.get_json(force=True)
        media_path = data.get("path")
        if not media_path or not is_allowed_media_path(media_path):
            abort(403)
        players = load_players()
        player_name = data.get("player") or ""
        exe = ""
        if player_name:
            for p in players:
                if p.get("name") == player_name:
                    exe = p.get("path", "")
                    break
        if not exe and players:
            exe = players[0].get("path", "")
        if not exe:
            exe = load_config().get("potplayer_path", "")
        if not exe or not Path(exe).exists():
            return jsonify({"ok": False, "error": "没有可用的播放器"}), 400
        try:
            proc = subprocess.Popen([exe, media_path], shell=False)
            return jsonify({"ok": True, "player": Path(exe).stem})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/players")
    def api_players():
        return jsonify(load_players())

    @app.route("/api/playback/current", methods=["GET"])
    def api_playback_current():
        """Return the current playing file path from PotPlayer's dpl file.

        This is used by the frontend to detect what PotPlayer is playing
        right now without polling.
        """
        try:
            from moviewall.player_monitor import get_current_playing, is_running
            return jsonify({
                "path": get_current_playing(),
                "monitor_active": is_running(),
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/api/open_folder", methods=["POST"])
    def api_open_folder():
        folder = request.get_json(force=True).get("folder")
        if not folder or not is_allowed_folder(folder):
            abort(403)
        if os.name == "nt":
            subprocess.Popen(["explorer", str(Path(folder).resolve())])
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "仅支持 Windows Explorer"}), 400

    @app.route("/api/config", methods=["GET"])
    def api_get_config():
        cfg = load_config()
        return jsonify({
            "categories": normalize_categories(),
            "library_root": cfg.get("library_root", ""),
        })

    @app.route("/api/config", methods=["PUT"])
    def api_update_config():
        data = request.get_json(force=True)
        cfg = load_config()
        for key in ("categories", "library_root", "players", "douban_enabled", "douban_id_overrides"):
            if key in data:
                cfg[key] = data[key]
        write_json(CONFIG_FILE, cfg)
        return jsonify({"ok": True})

    @app.route("/api/ratings", methods=["GET"])
    def api_get_ratings():
        return jsonify(load_all_ratings())

    @app.route("/api/ratings", methods=["PUT"])
    def api_set_rating():
        data = request.get_json(force=True)
        media_id = data.get("media_id")
        score = data.get("score")
        if not media_id or score is None:
            return jsonify({"ok": False, "error": "缺少 media_id 或 score"}), 400
        save_rating(media_id, float(score))
        return jsonify({"ok": True})

    @app.route("/api/ratings/<media_id>", methods=["DELETE"])
    def api_clear_rating(media_id):
        delete_rating(media_id)
        return jsonify({"ok": True})

    @app.route("/api/history", methods=["GET"])
    def api_get_history():
        return jsonify(load_all_history())

    @app.route("/api/history", methods=["PUT"])
    def api_record_history():
        data = request.get_json(force=True)
        media_id = data.get("media_id")
        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400
        raw_ts = data.get("played_at")
        # Normalise: frontend used to send ISO strings which break SQLite sorting
        if isinstance(raw_ts, str):
            try:
                raw_ts = time.mktime(time.strptime(raw_ts[:19], "%Y-%m-%dT%H:%M:%S"))
            except (ValueError, OverflowError):
                raw_ts = time.time()
        entry = {**data, "played_at": raw_ts or time.time()}
        save_history(entry)
        return jsonify({"ok": True})

    @app.route("/api/history/<media_id>", methods=["DELETE"])
    def api_clear_history(media_id):
        conn = get_conn()
        try:
            conn.execute("DELETE FROM history WHERE media_id=?", (media_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return jsonify({"ok": True})

    @app.route("/api/favorites", methods=["GET"])
    def api_get_favorites():
        return jsonify(load_all_favorites())

    @app.route("/api/favorites", methods=["PUT"])
    def api_toggle_favorite():
        data = request.get_json(force=True)
        media_id = data.get("media_id")
        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400
        action = toggle_favorite(media_id)
        return jsonify({"ok": True, "action": action})

    @app.route("/api/metadata/douban/<media_id>", methods=["PUT"])
    def api_set_douban_id(media_id):
        data = request.get_json(force=True)
        douban_id = data.get("douban_id", "").strip()
        manual_rating = data.get("rating")
        manual_synopsis = data.get("synopsis", "").strip()
        set_douban_id_override(media_id, douban_id)
        item = find_media_by_id(media_id)
        douban_data = None

        if douban_id:
            # Try auto-fetch (may fail due to Douban WAF)
            douban_data = fetch_douban_by_id(douban_id)
            if douban_data and item:
                save_douban_meta(media_id, douban_data)
                if douban_data.get("synopsis"):
                    tm = load_tmdb_meta(media_id)
                    if tm:
                        tm["overview"] = douban_data["synopsis"]
                        save_tmdb_meta(media_id, {**tm, "_season_data": tm.get("_season_data")})

        # If auto-fetch failed or user provided manual data, save manually
        if manual_rating is not None or manual_synopsis:
            conn = get_conn()
            try:
                existing = conn.execute("SELECT * FROM metadata_douban WHERE media_id=?", (media_id,)).fetchone()
                if existing:
                    rating = manual_rating if manual_rating is not None else existing["rating"]
                    synopsis = manual_synopsis if manual_synopsis else existing["synopsis"]
                    new_id = douban_id or existing["douban_id"]
                    conn.execute("""UPDATE metadata_douban SET rating=?, synopsis=?, douban_id=? WHERE media_id=?""",
                                 (rating, synopsis, new_id, media_id))
                else:
                    conn.execute("""INSERT INTO metadata_douban (media_id,douban_id,rating,synopsis,fetched_at)
                                    VALUES (?,?,?,?,?)""",
                                 (media_id, douban_id or None, manual_rating, manual_synopsis, time.time()))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            if manual_synopsis and item:
                tm = load_tmdb_meta(media_id)
                if tm:
                    tm["overview"] = manual_synopsis
                    save_tmdb_meta(media_id, {**tm, "_season_data": tm.get("_season_data")})

        return jsonify({"ok": True, "douban": douban_data})

    @app.route("/api/metadata/douban/<media_id>", methods=["DELETE"])
    def api_clear_douban_id(media_id):
        set_douban_id_override(media_id, "")
        conn = get_conn()
        try:
            conn.execute("DELETE FROM metadata_douban WHERE media_id=?", (media_id,))
            conn.execute("DELETE FROM metadata_douban_seasons WHERE show_id=?", (media_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return jsonify({"ok": True})

    @app.route("/api/update_single", methods=["POST"])
    def api_update_single():
        """Re-fetch metadata for a single item with full cache invalidation."""
        data = request.get_json(force=True)
        media_id = data.get("media_id", "").strip()
        douban_id = data.get("douban_id", "").strip()
        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400

        if douban_id:
            set_douban_id_override(media_id, douban_id)

        item = find_media_by_id(media_id)
        if item:
            from moviewall.metadata import clear_tmdb_cache
            clear_tmdb_cache(media_id, item.get("title", ""))
            log.info("UPDATE SINGLE: clearing cache for %s (%s)", media_id, item.get("title"))
            # force_refresh=True ensures old cache is bypassed
            attach_all_metadata(item, force_refresh=True)

        return jsonify({"ok": True, "media_id": media_id})
