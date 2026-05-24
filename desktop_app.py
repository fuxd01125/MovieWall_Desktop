import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from tkinter import Tk, messagebox

from werkzeug.serving import make_server
from moviewall import app

APP_TITLE = "MovieWall"


def find_free_port(start=5000, end=5099):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("没有可用端口，5000-5099 都被占用。")


class ServerThread(threading.Thread):
    def __init__(self, port):
        super().__init__(daemon=True)
        self.port = port
        self.server = make_server("127.0.0.1", port, app)
        self.context = app.app_context()
        self.context.push()

    def run(self):
        self.server.serve_forever()

    def shutdown(self):
        try:
            self.server.shutdown()
        except Exception:
            pass


def show_error(title, message):
    root = Tk()
    root.withdraw()
    messagebox.showerror(title, message)
    root.destroy()


def main():
    server = None
    try:
        try:
            import webview
        except Exception:
            show_error(APP_TITLE, "缺少 pywebview。请先运行 Install_Dependencies.bat 或 Build_EXE.bat。")
            return

        port = find_free_port()
        server = ServerThread(port)
        server.start()
        url = f"http://127.0.0.1:{port}/"

        for _ in range(40):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    break
            except OSError:
                time.sleep(0.1)

        icon_path = str(Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent / "MovieWall.ico")
        kwargs = dict(title=APP_TITLE, url=url, width=1280, height=820, min_size=(960, 640), confirm_close=False, text_select=True)
        try:
            webview.create_window(icon=icon_path, **kwargs)
        except TypeError:
            webview.create_window(**kwargs)
        webview.start(debug=False)

    except Exception:
        err = traceback.format_exc()
        try:
            log_path = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent / "MovieWall_error.log"
            log_path.write_text(err, encoding="utf-8")
        except Exception:
            pass
        show_error(APP_TITLE, "MovieWall 启动失败，错误已写入 MovieWall_error.log。")
    finally:
        if server:
            server.shutdown()
        os._exit(0)


if __name__ == "__main__":
    main()
