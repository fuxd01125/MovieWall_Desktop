"""Simple structured logging — request timing, scan timing, error reporting."""
import logging
import sys
import time

from moviewall.config import APP_DIR

_LOG_LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}

def setup_log(name="moviewall", level="INFO"):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(_LOG_LEVELS.get(level, logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    try:
        fh = logging.FileHandler(str(APP_DIR / "moviewall.log"), encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass
    return logger


log = setup_log()


class Timer:
    """Simple context manager for timing operations."""

    def __init__(self, name=""):
        self.name = name

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.elapsed = time.time() - self.start
        if self.elapsed > 1:
            log.info("%s took %.2fs", self.name, self.elapsed)
