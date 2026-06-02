import traceback

from utils.logger import (
    setup_logger
)


thread_logger = setup_logger(
    "thread_logger",
    "logs/errors/thread_errors.log"
)


def safe_thread_runner(
    target,
    thread_name
):

    def wrapped():

        try:

            target()

        except Exception:

            thread_logger.exception(
                f"{thread_name} crashed"
            )

            print(
                f"{thread_name} crashed"
            )

            traceback.print_exc()

    return wrapped