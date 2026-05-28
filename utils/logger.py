import logging
import os


def setup_logger(name, log_file, level=logging.INFO):

    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger(name)

    logger.setLevel(level)

    if not logger.handlers:

        file_handler = logging.FileHandler(log_file)

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s"
        )

        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger