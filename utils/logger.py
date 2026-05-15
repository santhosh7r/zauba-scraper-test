import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from config import LOGS_DIR, LOG_MAX_BYTES, LOG_BACKUP_COUNT

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

    # Rotating file handler — caps disk usage so an unattended VPS never
    # fills up: LOG_BACKUP_COUNT files of at most LOG_MAX_BYTES each.
    fh = RotatingFileHandler(
        os.path.join(LOGS_DIR, "scraper.log"),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_fmt)
    logger.addHandler(fh)

    return logger


log = get_logger()
