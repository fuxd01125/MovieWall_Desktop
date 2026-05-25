"""Flask routes — API endpoints backed by SQLite database."""
import json
import os
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

from flask import abort, jsonify, render_template, request, send_file

from moviewall.config import load_config, write_json, CONFIG_FILE, METADATA_CACHE_FILE, load_players, normalize_categories
from moviewall.database import (
    build_library_dict, load_all_ratings, load_all_history, load_all_favorites,
    save_rating, delete_rating, save_history, toggle_favorite,
    load_tmdb_meta, load_douban_meta, save_douban_meta,
)
from moviewall.douban import fetch_douban_by_id, set_douban_id_override, fetch_douban_meta
from moviewall.scanner import scan_library
from moviewall.metadata import attach_all_metadata

# ── Helpers ─────────────────────────────────────────────────────────

_scan_progress = {"progress": 0, "message": "", "done": False, "error": ""}


def _iter_media_items():
    lib = build_library_dict()
    for item in lib.get("items", []):
        yield item
        if item.get("type") == "show":
            for season in item.get("seasons", []):
                yield season
                for ep in season.get("episodes", []):
                    yield ep


def find_media_by_id(media_id):
    for item in _iter_media_items():
        if item.get("id") == media_id:
            return item
    return None


def is_allowed_media_path(path):
    try:
        target = str(Path(path).resolve())
    except Exception:
        return False
    for item in _iter_media_items():
        if item.get("path"):
            try:
                if str(Path(item["path"]).resolve()) == target:
                    return True
            except Exception:
                pass
    return False


def is_allowed_folder(folder):
    try:
        target = str(Path(folder).resolve())
    except Exception:
        return False
    for item in _iter_media_items():
        if item.get("folder"):
            try:
                if str(Path(item["folder"]).resolve()) == target:
                    return True
            except Exception:
                pass
    return False


# ── Route Registration ──────────────────────────────────────────────

def register_routes(app):

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/library")
    def api_library():
        return jsonify(build_library_dict())

    @app.route("/api/scan", methods=["POST"])
    def api_scan():
        force = request.args.get("force") == "1" or (request.get_json(silent=True) or {}).get("force")

        def _run():
            global _scan_progress
            _scan_progress = {"progress": 0, "message": "开始扫描...", "done": False, "error": ""}
            try:
                def cb(p, msg):
                    global _scan_progress
                    _scan_progress = {"progress": p, "message": msg, "done": False, "error": ""}
                scan_library(progress_callback=cb)
                _scan_progress["done"] = True
            except Exception as e:
                _scan_progress = {"progress": 1, "message": str(e), "done": True, "error": str(e)}

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return jsonify({"ok": True, "message": "扫描已启动"})

    @app.route("/api/scan/progress")
    def api_scan_progress():
        return jsonify(_scan_progress)

    @app.route("/api/update", methods=["POST"])
    def api_update_metadata():
        """Force re-fetch TMDB + Douban metadata for all items without re-scanning files."""
        # Clear cache to force re-fetch
        from moviewall.config import METADATA_CACHE_FILE
        try:
            if METADATA_CACHE_FILE.exists():
                METADATA_CACHE_FILE.unlink()
        except Exception:
            pass

        def _run():
            global _scan_progress
            from concurrent.futures import ThreadPoolExecutor, as_completed
            _scan_progress = {"progress": 0, "message": "开始更新元数据...", "done": False, "error": ""}
            lib = build_library_dict()
            items = lib.get("items", [])
            total = len(items)
            try:
                if total > 0:
                    max_workers = min(5, total)
                    with ThreadPoolExecutor(max_workers=max_workers) as pool:
                        futures = {pool.submit(attach_all_metadata, item): item for item in items}
                        done = 0
                        for future in as_completed(futures):
                            done += 1
                            item = futures[future]
                            _scan_progress = {"progress": done / total if total else 1,
                                              "message": f"更新: {item.get('display_title') or item.get('title')}",
                                              "done": False, "error": ""}
                            try:
                                future.result()
                            except Exception:
                                pass
                _scan_progress["done"] = True
            except Exception as e:
                _scan_progress = {"progress": 1, "message": str(e), "done": True, "error": str(e)}

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return jsonify({"ok": True, "message": "更新已启动"})

    @app.route("/api/artwork/<media_id>/<kind>")
    def api_artwork(media_id, kind):
        item = find_media_by_id(media_id)
        if not item:
            abort(404)
        art_path = item.get(kind)
        if not art_path:
            abort(404)
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
            subprocess.Popen([exe, media_path], shell=False)
            return jsonify({"ok": True, "player": Path(exe).stem})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/players")
    def api_players():
        return jsonify(load_players())

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
        entry = {**data, "played_at": data.get("played_at") or time.time()}
        save_history(entry)
        return jsonify({"ok": True})

    @app.route("/api/history/<media_id>", methods=["DELETE"])
    def api_clear_history(media_id):
        from moviewall.database import get_conn
        conn = get_conn()
        conn.execute("DELETE FROM history WHERE media_id=?", (media_id,))
        conn.commit()
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
        set_douban_id_override(media_id, douban_id)
        item = find_media_by_id(media_id)
        douban_data = None
        if douban_id:
            douban_data = fetch_douban_by_id(douban_id)
            if douban_data and item:
                save_douban_meta(media_id, douban_data)
                if douban_data.get("synopsis"):
                    from moviewall.database import load_tmdb_meta, save_tmdb_meta
                    tm = load_tmdb_meta(media_id)
                    if tm:
                        tm["overview"] = douban_data["synopsis"]
                        save_tmdb_meta(media_id, {**tm, "_season_data": tm.get("_season_data")})
        return jsonify({"ok": True, "douban": douban_data})

    @app.route("/api/metadata/douban/<media_id>", methods=["DELETE"])
    def api_clear_douban_id(media_id):
        set_douban_id_override(media_id, "")
        from moviewall.database import get_conn
        conn = get_conn()
        conn.execute("DELETE FROM metadata_douban WHERE media_id=?", (media_id,))
        conn.execute("DELETE FROM metadata_douban_seasons WHERE show_id=?", (media_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True})

    @app.route("/api/update_single", methods=["POST"])
    def api_update_single():
        """Re-fetch metadata for a single item (optionally with a custom douban_id)."""
        data = request.get_json(force=True)
        media_id = data.get("media_id", "").strip()
        douban_id = data.get("douban_id", "").strip()
        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400

        if douban_id:
            set_douban_id_override(media_id, douban_id)

        # Clear entire cache to force re-fetch
        try:
            if METADATA_CACHE_FILE.exists():
                METADATA_CACHE_FILE.unlink()
        except Exception:
            pass

        # Also delete existing DB metadata so attach_all_metadata re-fetches
        from moviewall.database import get_conn
        conn = get_conn()
        conn.execute("DELETE FROM metadata_douban WHERE media_id=?", (media_id,))
        conn.execute("DELETE FROM metadata_douban_seasons WHERE show_id=?", (media_id,))
        conn.execute("DELETE FROM metadata_tmdb WHERE media_id=?", (media_id,))
        conn.commit()
        conn.close()

        item = find_media_by_id(media_id)
        if item:
            attach_all_metadata(item)

        return jsonify({"ok": True, "media_id": media_id})
