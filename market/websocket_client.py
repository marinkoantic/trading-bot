import json
import time
import websocket

from core.models import TickEvent
from core.events import tick_queue
from core.state import SystemState

from market.heartbeat import heartbeat

from utils.logger import setup_logger


websocket_logger = setup_logger(
    "websocket_logger",
    "logs/websocket/websocket.log"
)


BINANCE_WS_URL = (
    "wss://stream.binance.com:9443/ws/"
    "luncusdt@aggTrade"
)


def on_message(ws, message):

    try:

        data = json.loads(message)

        tick = TickEvent(
            symbol="LUNCUSDT",

            price=float(data["p"]),

            quantity=float(data["q"]),

            timestamp=int(data["T"])
        )

        tick_queue.put(tick)

        heartbeat.update()

        SystemState.total_ticks_processed += 1

    except Exception as error:

        websocket_logger.error(
            f"Message processing error: {error}"
        )


def on_error(ws, error):

    websocket_logger.error(
        f"Websocket error: {error}"
    )


def on_close(ws, close_status_code, close_msg):

    websocket_logger.warning(
        "Websocket closed"
    )


def on_open(ws):

    websocket_logger.info(
        "Websocket connection established"
    )


def start_websocket():

    while True:

        try:

            ws = websocket.WebSocketApp(
                BINANCE_WS_URL,

                on_message=on_message,

                on_error=on_error,

                on_close=on_close,

                on_open=on_open
            )

            ws.run_forever()

        except Exception as error:

            websocket_logger.error(
                f"Reconnect error: {error}"
            )

        websocket_logger.info(
            "Reconnecting in 5 seconds..."
        )

        time.sleep(5)