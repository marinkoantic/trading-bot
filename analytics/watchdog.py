import time

from market.heartbeat import heartbeat

from utils.logger import setup_logger


watchdog_logger = setup_logger(
    "watchdog_logger",
    "logs/system/watchdog.log"
)


class Watchdog:

    def monitor(self):

        while True:

            if heartbeat.is_stale():

                watchdog_logger.warning(
                    "Websocket stale detected"
                )

            time.sleep(10)