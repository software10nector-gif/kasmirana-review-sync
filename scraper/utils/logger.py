"""
Console + rotating-file logger. In GitHub Actions, the console output is
what you see in the workflow run's log tab; the file handler is kept too
so it also works identically for local testing.
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from config import config

os.makedirs(config.log_dir, exist_ok=True)

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(config.log_level)
    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    file_handler = RotatingFileHandler(
        os.path.join(config.log_dir, "review_sync.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
