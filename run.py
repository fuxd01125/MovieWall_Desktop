import threading
import webbrowser

from moviewall import app
from moviewall.config import load_config

if __name__ == "__main__":
    if load_config().get("auto_open_browser", True):
        threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:5000/")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
