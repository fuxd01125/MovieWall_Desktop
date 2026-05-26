import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE_DIR = ROOT / "release"
DIST_DIR = RELEASE_DIR / "dist"
BUILD_DIR = ROOT / "build"
LOG_FILE = RELEASE_DIR / "build_error.log"
_SEP = ";" if os.name == "nt" else ":"


def log(text): print(text, flush=True)


def run(cmd, title=None):
    if title:
        log("")
        log(f"  {title}")
    log("  RUN: " + " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, cwd=str(ROOT), text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed (rc={result.returncode}): {' '.join(str(x) for x in cmd)}"
        )
    return result


def safe_rmtree(path):
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def copy_file(src, dst):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        log(f"  COPY: {src.name} -> {dst}")


def main():
    try:
        log("=" * 50)
        log(" MovieWall EXE Builder (--onefile)")
        log("=" * 50)
        log(f" Python: {sys.executable}")
        log(f" Root:   {ROOT}")

        # Step 1: Install dependencies
        run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            "[1/5] Installing dependencies",
        )

        # Step 2: Clean old build artifacts
        log("")
        log("[2/5] Cleaning old build files")
        safe_rmtree(BUILD_DIR)
        old_dist = ROOT / "dist"
        safe_rmtree(old_dist)
        old_release = ROOT / "release"
        safe_rmtree(old_release)

        # Step 3: Build with PyInstaller --onefile
        log("")
        log("[3/5] Building MovieWall.exe (--onefile)")
        add_data = []
        add_data.append(f"templates{_SEP}templates")
        add_data.append(f"static{_SEP}static")
        add_data.append(f"MovieWall.ico{_SEP}.")

        hidden_imports = [
            "webview.platforms.edgechromium",
            "certifi", "idna",
            "charset_normalizer",
            "urllib.parse", "urllib.request", "urllib.error",
            "http.cookiejar",
        ]
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--noconfirm", "--clean",
            "--onefile",
            "--noconsole",
            "--name", "MovieWall",
            "--icon", str(ROOT / "MovieWall.ico"),
            "--collect-all", "webview",
        ]
        for hi in hidden_imports:
            cmd.extend(["--hidden-import", hi])
        cmd.extend(["--collect-data", "certifi"])
        for ad in add_data:
            cmd.extend(["--add-data", ad])
        cmd.append(str(ROOT / "desktop_app.py"))
        run(cmd)

        # Step 4: Prepare release directory
        log("")
        log("[4/5] Preparing release directory")
        safe_rmtree(RELEASE_DIR)
        RELEASE_DIR.mkdir(parents=True, exist_ok=True)
        DIST_DIR.mkdir(parents=True, exist_ok=True)

        exe_src = ROOT / "dist" / "MovieWall.exe"
        if not exe_src.exists():
            raise RuntimeError(f"MovieWall.exe not found at: {exe_src}")

        exe_dst = DIST_DIR / "MovieWall.exe"
        shutil.copy2(exe_src, exe_dst)
        log(f"  COPY: MovieWall.exe -> {exe_dst}")

        # Copy config.json and icon alongside the exe
        for name in ["config.json", "MovieWall.ico"]:
            copy_file(ROOT / name, DIST_DIR / name)

        # Create logs directory
        (RELEASE_DIR / "logs").mkdir(exist_ok=True)

        exe_file = DIST_DIR / "MovieWall.exe"
        if not exe_file.exists():
            raise RuntimeError(f"MovieWall.exe was not found: {exe_file}")

        exe_size = exe_file.stat().st_size / (1024 * 1024)
        log("")
        log("=" * 50)
        log(" BUILD SUCCESS")
        log(f" EXE: {exe_file}")
        log(f" Size: {exe_size:.1f} MB")
        log("=" * 50)

    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LOG_FILE.write_text(err_msg, encoding="utf-8")
        log("")
        log("=" * 50)
        log(" BUILD FAILED")
        log(f" Reason: {e}")
        log(f" Log: {LOG_FILE}")
        log("=" * 50)
        input("Press Enter to exit...")
        raise


if __name__ == "__main__":
    main()
