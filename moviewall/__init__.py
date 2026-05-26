import atexit
import threading

from flask import Flask

from moviewall.config import PACKAGED_DIR


def create_app():
    app = Flask(
        __name__,
        template_folder=str(PACKAGED_DIR / "templates"),
        static_folder=str(PACKAGED_DIR / "static"),
    )
    from moviewall.routes import register_routes
    register_routes(app)

    # Start PotPlayer file monitor in background (non-blocking)
    _start_player_monitor(app)

    return app


def _start_player_monitor(app):
    """Start the background PotPlayer dpl/ini file monitor.

    Safe to call multiple times — the monitor is a singleton.
    """
    try:
        from moviewall.player_monitor import start_monitor

        # Run monitor startup in a separate thread so it doesn't
        # block the Flask dev server on first request.
        def _start():
            start_monitor()

        thread = threading.Thread(target=_start, daemon=True, name="PlayerMonitorInit")
        thread.start()

        # Ensure the monitor stops when the process exits
        def _cleanup():
            try:
                from moviewall.player_monitor import stop_monitor
                stop_monitor()
            except Exception:
                pass

        atexit.register(_cleanup)
    except Exception as exc:
        app.logger.warning("Player monitor not started: %s", exc)


app = create_app()
