import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist" / "MovieWall"
BUILD_DIR = ROOT / "build"
LOG_FILE = ROOT / "build_error.log"

def log(text): print(text, flush=True)

def run(cmd, title=None):
    if title:
        log("")
        log(title)
    log("RUN: " + " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, cwd=str(ROOT), text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(str(x) for x in cmd)}")

def safe_rmtree(path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)

def copy_file(src, dst):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

def copy_dir(src, dst):
    if src.exists():
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst)

def main():
    try:
        log("==========================================")
        log(" MovieWall Desktop EXE Builder V15")
        log("==========================================")
        log(f"Python: {sys.executable}")
        run([sys.executable, "-m", "pip", "install", "-r", "requirements_desktop.txt"], "[1/4] Installing dependencies")
        log("")
        log("[2/4] Cleaning old build files")
        safe_rmtree(BUILD_DIR)
        safe_rmtree(DIST_DIR)
        spec = ROOT / "MovieWall.spec"
        if spec.exists():
            spec.unlink()
        run([
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean", "--noconsole", "--onedir",
            "--name", "MovieWall",
            "--icon", "MovieWall.ico",
            "--collect-all", "webview",
            "--hidden-import", "webview.platforms.edgechromium",
            "desktop_app.py"
        ], "[3/4] Building MovieWall.exe")
        log("")
        log("[4/4] Copying runtime files")
        copy_dir(ROOT / "templates", DIST_DIR / "templates")
        copy_dir(ROOT / "static", DIST_DIR / "static")
        for name in ["app.py", "config.json", "local_metadata.json", "library.json", "metadata_cache.json", "MovieWall.ico"]:
            copy_file(ROOT / name, DIST_DIR / name)
        exe = DIST_DIR / "MovieWall.exe"
        if not exe.exists():
            raise RuntimeError(f"MovieWall.exe was not found: {exe}")
        log("")
        log("BUILD SUCCESS")
        log(f"Your app is here: {exe}")
    except Exception as e:
        LOG_FILE.write_text(str(e), encoding="utf-8")
        log("")
        log("BUILD FAILED")
        log(f"Reason: {e}")
        log(f"Log file: {LOG_FILE}")
        input("Press Enter to exit...")
        raise

if __name__ == "__main__":
    main()
