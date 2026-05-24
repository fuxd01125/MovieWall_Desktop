import os
import subprocess
import time
from pathlib import Path

from flask import abort, jsonify, render_template, request, send_file

from moviewall.config import load_config, load_library, read_ratings, write_ratings, read_history, write_history, read_favorites, write_favorites, load_players, normalize_categories, write_json, CONFIG_FILE
from moviewall.douban import get_douban_metadata_by_id, set_douban_id_override
from moviewall.metadata import attach_metadata
from moviewall.scanner import scan_library


def iter_media_items():
    for item in load_library().get("items", []):
        yield item
        if item.get("type") == "show":
            for season in item.get("seasons", []):
                yield season
                for ep in season.get("episodes", []):
                    yield ep


def find_media_by_id(media_id):
    for item in iter_media_items():
        if item.get("id") == media_id:
            return item
    return None


def is_allowed_media_path(path: str):
    try:
        target = str(Path(path).resolve())
    except Exception:
        return False
    for item in iter_media_items():
        if item.get("path"):
            try:
                if str(Path(item["path"]).resolve()) == target:
                    return True
            except Exception:
                pass
    return False


def is_allowed_folder(folder: str):
    try:
        target = str(Path(folder).resolve())
    except Exception:
        return False
    for item in iter_media_items():
        if item.get("folder"):
            try:
                if str(Path(item["folder"]).resolve()) == target:
                    return True
            except Exception:
                pass
    return False


def register_routes(app):

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/library")
    def api_library():
        return jsonify(load_library())

    @app.route("/api/scan", methods=["POST"])
    def api_scan():
        force = request.args.get("force") == "1" or (request.get_json(silent=True) or {}).get("force")
        return jsonify(scan_library(force=force))

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
            return jsonify({"ok": False, "error": "没有可用的播放器，请检查 config.json 中的 players 或 potplayer_path"}), 400
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
        return jsonify(read_ratings())

    @app.route("/api/ratings", methods=["PUT"])
    def api_set_rating():
        data = request.get_json(force=True)
        media_id = data.get("media_id")
        score = data.get("score")
        if not media_id or score is None:
            return jsonify({"ok": False, "error": "缺少 media_id 或 score"}), 400
        ratings = read_ratings()
        ratings[media_id] = {"score": float(score), "rated_at": time.time()}
        write_ratings(ratings)
        return jsonify({"ok": True})

    @app.route("/api/ratings/<media_id>", methods=["DELETE"])
    def api_clear_rating(media_id):
        ratings = read_ratings()
        ratings.pop(media_id, None)
        write_ratings(ratings)
        return jsonify({"ok": True})

    @app.route("/api/history", methods=["GET"])
    def api_get_history():
        return jsonify(read_history())

    @app.route("/api/history", methods=["PUT"])
    def api_record_history():
        data = request.get_json(force=True)
        media_id = data.get("media_id")
        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400
        history = read_history()
        entry = {**data, "played_at": data.get("played_at") or time.time()}
        history[media_id] = entry
        history["__last"] = entry
        write_history(history)
        return jsonify({"ok": True})

    @app.route("/api/history/<media_id>", methods=["DELETE"])
    def api_clear_history(media_id):
        history = read_history()
        history.pop(media_id, None)
        write_history(history)
        return jsonify({"ok": True})

    @app.route("/api/metadata/douban/<media_id>", methods=["PUT"])
    def api_set_douban_id(media_id):
        data = request.get_json(force=True)
        douban_id = data.get("douban_id", "").strip()
        set_douban_id_override(media_id, douban_id)
        item = find_media_by_id(media_id)
        if item and douban_id:
            douban = get_douban_metadata_by_id(douban_id)
            if douban:
                if "metadata" not in item:
                    item["metadata"] = {}
                item["metadata"]["douban"] = douban
                if douban.get("synopsis") and item["metadata"].get("tmdb"):
                    item["metadata"]["tmdb"]["overview"] = douban["synopsis"]
                try:
                    from moviewall.config import save_library, load_library
                    lib = load_library()
                    for i in lib.get("items", []):
                        if i["id"] == media_id:
                            i["metadata"] = item["metadata"]
                            break
                    save_library(lib)
                except Exception:
                    pass
                return jsonify({"ok": True, "douban": douban})
        return jsonify({"ok": True, "douban": None})

    @app.route("/api/metadata/douban/<media_id>", methods=["DELETE"])
    def api_clear_douban_id(media_id):
        set_douban_id_override(media_id, "")
        item = find_media_by_id(media_id)
        if item and "metadata" in item and "douban" in item["metadata"]:
            del item["metadata"]["douban"]
            try:
                from moviewall.config import save_library, load_library
                lib = load_library()
                for i in lib.get("items", []):
                    if i["id"] == media_id:
                        i["metadata"] = item["metadata"]
                        break
                save_library(lib)
            except Exception:
                pass
        return jsonify({"ok": True})

    @app.route("/api/favorites", methods=["GET"])
    def api_get_favorites():
        return jsonify(read_favorites())

    @app.route("/api/favorites", methods=["PUT"])
    def api_toggle_favorite():
        data = request.get_json(force=True)
        media_id = data.get("media_id")
        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400
        favs = read_favorites()
        if media_id in favs:
            favs.remove(media_id)
            msg = "removed"
        else:
            favs.append(media_id)
            msg = "added"
        write_favorites(favs)
        return jsonify({"ok": True, "action": msg})
