import logging
from logging.handlers import RotatingFileHandler
import os


def create_rotating_logger(
    name,
    log_file,
    max_bytes=5_000_000,
    backup_count=5
):

    os.makedirs(
        os.path.dirname(log_file),
        exist_ok=True
    )

    logger = logging.getLogger(name)

    logger.setLevel(logging.INFO)

    if not logger.handlers:

        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )

        handler.setFormatter(formatter)

        logger.addHandler(handler)

    return logger