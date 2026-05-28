import time
import websocket

from market.reconnect_manager import reconnect_manager
from market.websocket_client import on_message

from utils.logger import setup_logger


system_logger = setup_logger(
    "system_logger",
    "logs/system/system.log"
)


BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@trade"


def start_market_stream():

    while True:

        try:

            ws = websocket.WebSocketApp(
                BINANCE_WS_URL,
                on_message=on_message
            )

            system_logger.info("Connecting to Binance websocket...")

            ws.run_forever()

        except Exception as e:

            system_logger.error(f"Websocket crashed: {e}")

        backoff = reconnect_manager.get_backoff_time()

        system_logger.warning(
            f"Reconnect in {backoff} seconds..."
        )

        time.sleep(backoff)