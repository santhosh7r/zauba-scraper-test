import logging
import os
import sys
from config import LOGS_DIR

os.makedirs(LOGS_DIR, exist_ok=True)

_fmt = logging.Formatter(
    fmt="[%(asctime)s] %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def get_logger(name: str = "zauba") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_fmt)
    logger.addHandler(ch)

    # File handler
    fh = logging.FileHandler(
        os.path.join(LOGS_DIR, "scraper.log"),
        encoding="utf-8"
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_fmt)
    logger.addHandler(fh)

    return logger

log = get_logger()
