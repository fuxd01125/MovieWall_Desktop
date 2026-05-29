"""Flask routes — API endpoints backed by SQLite database."""
import json
import os
import shutil
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
    save_douban_meta, get_conn, delete_media, delete_season,
)
from moviewall.douban import fetch_douban_by_id, set_douban_id_override
from moviewall.scanner import scan_library
from moviewall.metadata import attach_all_metadata

# ── Helpers ─────────────────────────────────────────────────────────

_scan_progress = {"progress": 0, "message": "", "done": False, "error": ""}
_scan_lock = threading.Lock()


def find_media_by_id(media_id):
    for item in build_library_dict().get("items", []):
        if item.get("id") == media_id:
            return item
    return None


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


# ── Settings Schema ────────────────────────────────────────────────

SETTINGS_SCHEMA = {
    "library_root":         {"default": "",      "type": "string",  "label": "媒体库路径",       "section": "library",  "desc": "媒体文件的根目录路径"},
    "categories":           {"default": {},      "type": "dict",    "label": "目录分类",         "section": "library",  "desc": "文件夹名到显示名的映射"},
    "generate_thumbnails":  {"default": True,    "type": "bool",    "label": "生成缩略图",       "section": "library",  "desc": "扫描时自动生成视频缩略图"},
    "thumbnail_second":     {"default": 60,      "type": "int",     "label": "缩略图截取秒数",   "section": "library",  "desc": "从视频的第几秒截取缩略图"},
    "metadata_enabled":     {"default": True,    "type": "bool",    "label": "启用元数据",       "section": "tmdb",     "desc": "自动从 TMDB 获取影视信息"},
    "tmdb_api_key":         {"default": "",      "type": "string",  "label": "TMDB API Key",    "section": "tmdb",     "desc": "TMDB API 密钥，可在 themoviedb.org 申请"},
    "tmdb_language":        {"default": "zh-CN", "type": "string",  "label": "TMDB 语言",        "section": "tmdb",     "desc": "TMDB 返回数据的语言，如 zh-CN、en-US"},
    "metadata_cache_days":  {"default": 30,      "type": "int",     "label": "元数据缓存天数",   "section": "tmdb",     "desc": "缓存多少天后重新请求 TMDB 数据"},
    "douban_enabled":       {"default": True,    "type": "bool",    "label": "启用豆瓣",         "section": "douban",   "desc": "自动获取豆瓣评分和简介"},
    "douban_request_delay": {"default": 0.5,     "type": "float",  "label": "豆瓣请求延迟(秒)", "section": "douban",   "desc": "每次豆瓣请求的间隔，避免被封"},
    "players":              {"default": [],      "type": "list",    "label": "播放器列表",       "section": "player",   "desc": "可用的媒体播放器"},
    "ffmpeg_path":          {"default": "ffmpeg","type": "string",  "label": "FFmpeg 路径",      "section": "advanced", "desc": "FFmpeg 可执行文件路径，用于生成缩略图"},
    "history_limit":        {"default": 500,     "type": "int",     "label": "历史记录上限",     "section": "advanced", "desc": "最多保留多少条播放历史记录"},
    "log_level":            {"default": "INFO",  "type": "select",  "label": "日志级别",         "section": "advanced", "desc": "日志输出级别，DEBUG 最详细", "options": ["DEBUG", "INFO", "WARNING", "ERROR"]},
    "enable_file_log":      {"default": True,    "type": "bool",    "label": "启用文件日志",     "section": "advanced", "desc": "将日志写入 moviewall.log 文件"},
    "auto_open_browser":    {"default": True,    "type": "bool",    "label": "自动打开浏览器",   "section": "advanced", "desc": "启动时自动在浏览器中打开"},
}

_RESCAN_KEYS = {"library_root", "categories", "generate_thumbnails", "thumbnail_second"}
_RESTART_KEYS = {"log_level", "enable_file_log", "auto_open_browser"}


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
        # Prevent browser caching of API responses to ensure fresh data
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
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
            success_count = 0
            fail_count = 0
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
                                success_count += 1
                            except Exception as e:
                                fail_count += 1
                                log.error("UPDATE FAILED: item=%s error=%s", item.get("id"), e)
                with _scan_lock:
                    _scan_progress["done"] = True
                    if fail_count > 0:
                        _scan_progress["message"] = f"完成: {success_count}成功, {fail_count}失败"
                    else:
                        _scan_progress["message"] = f"完成: {success_count}项已更新"
            except Exception as e:
                with _scan_lock:
                    _scan_progress = {"progress": 1, "message": str(e), "done": True, "error": str(e)
                                      if total == 0 else f"部分更新: {success_count}成功, 失败: {str(e)}"}

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
            # Small delay to verify the process started successfully
            import time as _time
            _time.sleep(0.3)
            if proc.poll() is not None:
                return jsonify({"ok": False, "error": "播放器启动失败"}), 500
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

    @app.route("/api/delete_media", methods=["POST"])
    def api_delete_media():
        data = request.get_json(force=True)
        media_id = data.get("media_id", "").strip()
        scope = data.get("scope", "show")  # "show" or "season"
        season_number = data.get("season_number")

        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400

        item = find_media_by_id(media_id)
        if not item:
            return jsonify({"ok": False, "error": "媒体不存在"}), 404

        cfg = load_config()
        library_root = cfg.get("library_root", "")

        if scope == "season" and season_number is not None:
            # Season-scoped deletion: find the season folder
            season_folder = None
            for s in item.get("seasons", []):
                if s.get("season_number") == season_number:
                    season_folder = s.get("folder", "")
                    break

            if not season_folder:
                return jsonify({"ok": False, "error": "未找到该季的目录路径"}), 400

            # Safety checks
            if library_root:
                root_resolved = Path(library_root).resolve()
                target_resolved = Path(season_folder).resolve()
                if not target_resolved.is_relative_to(root_resolved):
                    return jsonify({"ok": False, "error": "路径不在媒体库范围内"}), 403
                if target_resolved == root_resolved:
                    return jsonify({"ok": False, "error": "不能删除媒体库根目录"}), 403

            # Delete season folder from disk
            try:
                target = Path(season_folder).resolve()
                if target.exists():
                    shutil.rmtree(str(target))
                    log.info("DELETE SEASON: removed folder %s", target)
            except Exception as e:
                return jsonify({"ok": False, "error": "删除文件失败: " + str(e)}), 500

            # Clean up season-scoped DB records
            delete_season(media_id, season_number)
            log.info("DELETE SEASON: cleaned DB for show=%s season=%s", media_id, season_number)

            return jsonify({"ok": True, "scope": "season"})
        else:
            # Full show/movie deletion
            folder = item.get("folder", "")
            if not folder:
                return jsonify({"ok": False, "error": "无文件夹路径"}), 400

            # Safety checks
            if library_root:
                root_resolved = Path(library_root).resolve()
                target_resolved = Path(folder).resolve()
                if not target_resolved.is_relative_to(root_resolved):
                    return jsonify({"ok": False, "error": "路径不在媒体库范围内"}), 403
                if target_resolved == root_resolved:
                    return jsonify({"ok": False, "error": "不能删除媒体库根目录"}), 403

            # Delete folder from disk
            try:
                target = Path(folder).resolve()
                if target.exists():
                    shutil.rmtree(str(target))
                    log.info("DELETE MEDIA: removed folder %s", target)
            except Exception as e:
                return jsonify({"ok": False, "error": "删除文件失败: " + str(e)}), 500

            # Clean up database
            delete_media(media_id)
            log.info("DELETE MEDIA: cleaned DB for %s", media_id)

            # Clean up douban_id_overrides
            overrides = cfg.get("douban_id_overrides", {})
            if media_id in overrides:
                del overrides[media_id]
                cfg["douban_id_overrides"] = overrides
                write_json(CONFIG_FILE, cfg)

            return jsonify({"ok": True, "scope": "show"})

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

    @app.route("/api/settings", methods=["GET"])
    def api_get_settings():
        cfg = load_config()
        settings = {}
        for key, schema in SETTINGS_SCHEMA.items():
            settings[key] = cfg.get(key, schema["default"])
        return jsonify({"settings": settings, "schema": SETTINGS_SCHEMA})

    @app.route("/api/settings", methods=["POST"])
    def api_save_settings():
        data = request.get_json(force=True)
        cfg = load_config()
        restart_required = False
        rescan_required = False
        for key, value in data.items():
            if key not in SETTINGS_SCHEMA:
                continue
            schema = SETTINGS_SCHEMA[key]
            expected = schema["type"]
            if expected == "bool" and not isinstance(value, bool):
                return jsonify({"ok": False, "error": key + " 必须是布尔值"}), 400
            if expected in ("int", "float") and not isinstance(value, (int, float)):
                return jsonify({"ok": False, "error": key + " 必须是数字"}), 400
            if expected in ("string", "select") and not isinstance(value, str):
                return jsonify({"ok": False, "error": key + " 必须是字符串"}), 400
            if expected == "select" and value not in schema.get("options", []):
                return jsonify({"ok": False, "error": key + " 值不在可选范围内"}), 400
            cfg[key] = value
            if key in _RESTART_KEYS:
                restart_required = True
            if key in _RESCAN_KEYS:
                rescan_required = True
        write_json(CONFIG_FILE, cfg)
        settings = {}
        for key, schema in SETTINGS_SCHEMA.items():
            settings[key] = cfg.get(key, schema["default"])
        return jsonify({
            "ok": True,
            "settings": settings,
            "restart_required": restart_required,
            "rescan_required": rescan_required,
        })

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

    @app.route("/api/person/<person_id>")
    def api_person(person_id):
        """Return person details plus all local media they appear in."""
        conn = get_conn()
        try:
            person = conn.execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()
            if not person:
                abort(404)
            person_dict = dict(person)

            # Parse raw JSON and also try TMDB person fetch for full details
            raw = person_dict.get("raw")
            raw_data = {}
            if raw:
                try:
                    raw_data = json.loads(raw) if isinstance(raw, str) else {}
                except (json.JSONDecodeError, TypeError):
                    pass

            # Try to fetch full person details from TMDB if not in raw
            source_id = person_dict.get("source_id", "").strip()
            tmdb_key = (load_config().get("tmdb_api_key") or "").strip()
            if source_id and tmdb_key:
                try:
                    import urllib.request
                    url = f"https://api.themoviedb.org/3/person/{source_id}?language={load_config().get('tmdb_language', 'zh-CN')}&api_key={tmdb_key}"
                    req = urllib.request.Request(url, headers={"User-Agent": "MovieWall/15"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        tmdb_person = json.loads(resp.read().decode("utf-8"))
                        if tmdb_person.get("name"):
                            person_dict["biography"] = tmdb_person.get("biography", "")
                            person_dict["birthday"] = tmdb_person.get("birthday", "")
                            person_dict["deathday"] = tmdb_person.get("deathday", "")
                            person_dict["place_of_birth"] = tmdb_person.get("place_of_birth", "")
                            person_dict["also_known_as"] = tmdb_person.get("also_known_as", [])
                            person_dict["homepage"] = tmdb_person.get("homepage", "")
                            # Update profile_url with higher-res version if available
                            if tmdb_person.get("profile_path"):
                                person_dict["profile_url"] = f"https://image.tmdb.org/t/p/w500{tmdb_person['profile_path']}"
                            raw_data = tmdb_person  # Use full data
                except Exception as e:
                    log.warning("TMDB person fetch failed for %s: %s", source_id, e)

            # Fallback to raw credit data fields if TMDB fetch failed
            if not person_dict.get("biography"):
                person_dict["biography"] = raw_data.get("biography", "")
            if not person_dict.get("birthday"):
                person_dict["birthday"] = raw_data.get("birthday", "")
            if not person_dict.get("deathday"):
                person_dict["deathday"] = raw_data.get("deathday", "")
            if not person_dict.get("place_of_birth"):
                person_dict["place_of_birth"] = raw_data.get("place_of_birth", "")
            if not person_dict.get("also_known_as"):
                person_dict["also_known_as"] = raw_data.get("also_known_as", [])

            person_dict.pop("raw", None)
            person_dict.pop("updated_at", None)

            # Credits joined with media for works list — deduplicate by media_id
            works = conn.execute("""
                SELECT c.scope, c.character, c.job, c.department,
                       m.id as media_id, m.title as media_title, m.media_type,
                       m.poster, m.year,
                       COALESCE(m.display_title, m.title) as display_title
                FROM credits c
                JOIN media m ON m.id = c.media_id
                WHERE c.person_id = ?
                GROUP BY m.id
                ORDER BY m.title COLLATE NOCASE
            """, (person_id,)).fetchall()
            person_dict["works"] = [dict(w) for w in works]

        except Exception:
            raise
        finally:
            conn.close()
        return jsonify(person_dict)

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
            douban_data = fetch_douban_by_id(douban_id)
            if douban_data and item:
                save_douban_meta(media_id, douban_data)

        # Save manual data if provided (separate from TMDB overview)
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
        """Re-fetch metadata for a single item with full cache invalidation.
        Clears all cache layers (metadata_cache.json + DB), re-fetches
        TMDB + Douban, and returns the updated item data.
        """
        data = request.get_json(force=True)
        media_id = data.get("media_id", "").strip()
        douban_id = data.get("douban_id", "").strip()
        if not media_id:
            return jsonify({"ok": False, "error": "缺少 media_id"}), 400

        if douban_id:
            set_douban_id_override(media_id, douban_id)

        item = find_media_by_id(media_id)
        if not item:
            return jsonify({"ok": False, "error": "媒体不存在"}), 404

        from moviewall.metadata import clear_tmdb_cache
        clear_tmdb_cache(media_id, item.get("title", ""))
        log.info("UPDATE SINGLE: clearing cache for %s (%s)", media_id, item.get("title"))

        # Force-refresh TMDB + Douban metadata
        attach_all_metadata(item, force_refresh=True)

        # Return the freshly updated item
        updated = find_media_by_id(media_id)
        return jsonify({"ok": True, "media_id": media_id, "item": updated})
