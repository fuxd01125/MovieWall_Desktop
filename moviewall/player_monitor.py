"""PotPlayer file monitor — syncs play history from dpl/ini files in real-time.

Uses **watchdog** (filesystem events) to detect PotPlayer state changes
instead of polling.  Falls back to periodic polling if watchdog is not
available.

Watched files
-------------
1. ``{PotPlayerDir}\\Playlist\\PotPlayerMini64.dpl`` (playlist)
   Contains ``playname=<path>`` — the *current* playing file.
   Updated when: file changes, player opens/closes, playlist changes.

2. ``{PotPlayerDir}\\PotPlayerMini64.ini`` or
   ``%%APPDATA%%\\PotPlayer\\PotPlayerMini64.ini`` (config)
   Contains ``[RememberPlaybackPos]`` with ``path=seconds`` entries.
   Updated periodically during playback.

Architecture
------------
- A watchdog ``Observer`` watches the PotPlayer ``Playlist/`` directory.
- On every ``.dpl`` modify event, the file is re-parsed and the database
  is updated if ``playname`` changed.
- Similarly for ``.ini`` — progress is extracted from ``[RememberPlaybackPos]``.
- The monitor runs in a daemon thread; it never blocks the main thread.
"""
import re
import threading
import time
from pathlib import Path

from moviewall.log import log

# ── Regex patterns ────────────────────────────────────────────────────

_PLAYNAME_RE = re.compile(r"^playname=(.+)$", re.IGNORECASE)
_PLAYTIME_RE = re.compile(r"^playtime=(\d+)$", re.IGNORECASE)
_INI_PROGRESS_RE = re.compile(r"^(.+)=(\d+)$")

# ── Watchdog availability ─────────────────────────────────────────────

_HAVE_WATCHDOG = False
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    _HAVE_WATCHDOG = True
except ImportError:
    pass

# ── Singleton state ───────────────────────────────────────────────────

_observer = None
_stop_event = threading.Event()
_worker_thread = None

# Deduplication: avoid re-syncing the same state
_last_synced_playname = None
_last_synced_playtime = None
_last_ini_mtime = 0
_lock = threading.Lock()


# ═══════════════════════════════════════════════════════════════════════
#  Path resolution
# ═══════════════════════════════════════════════════════════════════════

def _get_potplayer_dpl_path():
    """Return the dpl file path from config (primary) or derived from player exe.

    Reads ``potplayer_dpl_path`` from ``config.json`` first.
    Falls back to ``{exe_dir}/Playlist/{exe_stem}.dpl`` for backward compat.

    Returns ``None`` if neither source yields a valid path.
    """
    from moviewall.config import get_potplayer_dpl_path as _cfg_dpl

    path = _cfg_dpl()
    if path and Path(path).exists():
        return path
    return None


# ═══════════════════════════════════════════════════════════════════════
#  DPL parser
# ═══════════════════════════════════════════════════════════════════════

def _read_dpl(dpl_path):
    """Parse a PotPlayer .dpl file and return ``(playname, playtime_ms)``.

    Returns ``(None, None)`` if the file cannot be read.
    """
    try:
        with open(dpl_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (OSError, IOError):
        try:
            with open(dpl_path, "r", encoding="utf-16-le") as f:
                content = f.read()
        except (OSError, IOError):
            return None, None

    playname = None
    playtime = None
    for line in content.splitlines():
        line = line.strip()
        m = _PLAYNAME_RE.match(line)
        if m:
            playname = m.group(1).strip()
        m = _PLAYTIME_RE.match(line)
        if m:
            playtime = int(m.group(1))

    return playname, playtime


def _read_ini_progress(ini_path, target_path):
    """Read playback position from PotPlayer .ini ``[RememberPlaybackPos]``.

    Args:
        ini_path: Path to the .ini file.
        target_path: The file path to look up.

    Returns:
        Position in seconds, or 0 if not found.
    """
    try:
        with open(ini_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, IOError):
        return 0

    in_section = False
    normalised_target = target_path.replace("/", "\\").lower()
    for line in lines:
        line = line.strip()
        if line.strip() == "[RememberPlaybackPos]":
            in_section = True
            continue
        if in_section:
            if line.startswith("["):
                break
            m = _INI_PROGRESS_RE.match(line)
            if m:
                key = m.group(1).strip()
                if key.replace("/", "\\").lower() == normalised_target:
                    return int(m.group(2))
    return 0


# ═══════════════════════════════════════════════════════════════════════
#  Database sync
# ═══════════════════════════════════════════════════════════════════════

def _lookup_media_by_path(filepath):
    """Find the media_id, season_id, episode_id for a given file path.

    Returns a dict with keys ``media_id``, ``season_id``, ``episode_id``,
    ``show_title``, ``episode_title``, ``season_number``, ``episode_number``,
    ``label``, ``short_label`` or ``None``.
    """
    from moviewall.database import get_conn

    normalised = filepath.replace("/", "\\")
    conn = get_conn()
    try:
        # Try exact path match first
        row = conn.execute(
            "SELECT * FROM episodes WHERE path=? OR path=?",
            (filepath, normalised),
        ).fetchone()
        if not row:
            # Try matching by filename
            fname = filepath.split("\\")[-1].split("/")[-1]
            row = conn.execute(
                "SELECT * FROM episodes WHERE path LIKE ? OR path LIKE ?",
                ("%/" + fname, "%\\" + fname),
            ).fetchone()
        if not row:
            return None

        ep = dict(row)
        # Get show info
        show = conn.execute(
            "SELECT id, display_title, title FROM media WHERE id=?",
            (ep["show_id"],),
        ).fetchone()
        if not show:
            return None

        show_title = show["display_title"] or show["title"] or ""
        sn = ep["season_number"] or 0
        en = ep["episode_number"] or 0
        short = f"S{sn:02d}E{en:02d}"

        return {
            "media_id": ep["show_id"],
            "season_id": ep["season_id"],
            "episode_id": ep["id"],
            "show_title": show_title,
            "episode_title": ep["title"] or "",
            "season_number": sn,
            "episode_number": en,
            "path": ep["path"],
            "short_label": short,
            "label": f"{show_title} · {short}" if show_title else short,
        }
    finally:
        conn.close()


def _sync_to_history(playname, playtime_ms):
    """Write the currently-playing episode into the history table.

    Args:
        playname: Full file path from the dpl file.
        playtime_ms: Current playback position in milliseconds (may be ``None``).
    """
    info = _lookup_media_by_path(playname)
    if not info:
        log.debug("PLAYER MONITOR: no DB match for %s", playname)
        return False

    from moviewall.database import save_history, update_history_progress

    now = time.time()
    duration_sec = 0
    progress_sec = (playtime_ms / 1000) if playtime_ms else 0

    save_history({
        "media_id": info["media_id"],
        "episode_id": info["episode_id"],
        "path": info["path"],
        "title": info["episode_title"],
        "show_title": info["show_title"],
        "season_number": info["season_number"],
        "episode_number": info["episode_number"],
        "label": info["label"],
        "short_label": info["short_label"],
        "played_at": now,
    })

    # Also update progress in the same row
    if progress_sec > 0:
        update_history_progress(
            info["media_id"], info["episode_id"],
            progress_sec, duration_sec, info["path"],
        )

    log.info(
        "PLAYER SYNC: %s media_id=%s path=%s",
        info["short_label"], info["media_id"], playname,
    )
    return True


# ═══════════════════════════════════════════════════════════════════════
#  Watchdog-based monitoring
# ═══════════════════════════════════════════════════════════════════════

def _process_dpl(dpl_path):
    """Read the dpl file and sync if the playname or playtime changed.

    - If ``playname`` changed (new file): full sync to history.
    - If only ``playtime`` changed (same file): update progress only.
    - If nothing changed: skip.
    """
    global _last_synced_playname, _last_synced_playtime

    playname, playtime_ms = _read_dpl(dpl_path)
    if not playname:
        return

    with _lock:
        if playname == _last_synced_playname and playtime_ms == _last_synced_playtime:
            return  # nothing changed

        if playname == _last_synced_playname and playtime_ms != _last_synced_playtime:
            # Same file, only progress changed — update progress
            _last_synced_playtime = playtime_ms
            progress_sec = playtime_ms / 1000 if playtime_ms else 0
            if progress_sec > 0:
                info = _lookup_media_by_path(playname)
                if info:
                    from moviewall.database import update_history_progress
                    update_history_progress(
                        info["media_id"], info["episode_id"],
                        progress_sec, 0, info["path"],
                    )
                    log.debug(
                        "PLAYER PROGRESS: %s → %.0fs",
                        info["short_label"], progress_sec,
                    )
            return

        # File changed — full sync
        _last_synced_playname = playname
        _last_synced_playtime = playtime_ms

    _sync_to_history(playname, playtime_ms)


class _DplEventHandler(FileSystemEventHandler):
    """Watchdog event handler for PotPlayer .dpl file changes."""

    def __init__(self, dpl_path):
        super().__init__()
        self.dpl_path = str(Path(dpl_path).resolve())

    def on_modified(self, event):
        if not event.is_directory:
            event_path = str(Path(event.src_path).resolve())
            if event_path == self.dpl_path:
                # Small delay to let PotPlayer finish writing
                time.sleep(0.3)
                _process_dpl(self.dpl_path)


# ═══════════════════════════════════════════════════════════════════════
#  Fallback poller (when watchdog is not available)
# ═══════════════════════════════════════════════════════════════════════

def _poller_worker(dpl_path, interval=3):
    """Periodically read the dpl file as a fallback when watchdog is not available."""
    while not _stop_event.is_set():
        try:
            _process_dpl(dpl_path)
        except Exception:
            log.exception("PLAYER MONITOR: poller error")
        _stop_event.wait(interval)


# ═══════════════════════════════════════════════════════════════════════
#  Public API
# ═══════════════════════════════════════════════════════════════════════

def start_monitor(paths=None):
    """Start the PotPlayer file monitor in a background daemon thread.

    Args:
        paths: Dict with keys ``dpl``, ``ini`` (optional).
               If ``None``, paths are auto-resolved from config.

    Returns ``True`` if the monitor started, ``False`` otherwise.
    """
    global _observer, _worker_thread

    if _observer or _worker_thread:
        log.info("PLAYER MONITOR: already running")
        return True

    if paths is None:
        dpl_path = _get_potplayer_dpl_path()
    elif isinstance(paths, dict):
        dpl_path = paths.get("dpl", "")
    else:
        dpl_path = paths

    if not dpl_path or not Path(dpl_path).parent.exists():
        log.warning("PLAYER MONITOR: dpl not found: %s", dpl_path)
        return False

    log.info("PLAYER MONITOR: starting — dpl=%s", dpl_path)

    if _HAVE_WATCHDOG:
        watch_dir = str(Path(dpl_path).parent)
        event_handler = _DplEventHandler(dpl_path)
        _observer = Observer()
        _observer.schedule(event_handler, watch_dir, recursive=False)
        _observer.daemon = True
        _observer.start()
        log.info("PLAYER MONITOR: watchdog observer started on %s", watch_dir)
    else:
        log.info("PLAYER MONITOR: watchdog not available, using poller")
        _worker_thread = threading.Thread(
            target=_poller_worker,
            args=(dpl_path,),
            daemon=True,
            name="PlayerMonitorPoller",
        )
        _worker_thread.start()

    # Do an initial sync on startup
    try:
        _process_dpl(dpl_path)
    except Exception:
        log.exception("PLAYER MONITOR: initial sync error")

    return True


def stop_monitor():
    """Stop the file monitor (observer and poller thread)."""
    global _observer, _worker_thread

    if _observer:
        log.info("PLAYER MONITOR: stopping watchdog observer")
        _observer.stop()
        _observer.join(timeout=5)
        _observer = None

    _stop_event.set()
    if _worker_thread:
        _worker_thread.join(timeout=5)
        _worker_thread = None

    log.info("PLAYER MONITOR: stopped")


def get_current_playing():
    """Return the current playing file path from the dpl file.

    Returns ``None`` if PotPlayer is not playing or the dpl is unreadable.
    """
    dpl_path = _get_potplayer_dpl_path()
    if not dpl_path:
        return None
    playname, _ = _read_dpl(dpl_path)
    return playname


def is_running():
    """Check if the monitor is active."""
    if _observer:
        return _observer.is_alive()
    if _worker_thread:
        return _worker_thread.is_alive()
    return False
