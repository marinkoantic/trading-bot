import time

from core.models import CandleEvent
from core.events import tick_queue, candle_queue
from core.state import SystemState

from candles.timeframes import TIMEFRAMES
from candles.candle_store import CandleStore

from utils.logger import setup_logger


candle_logger = setup_logger(
    "candle_logger",
    "logs/system/candles.log"
)


candle_store = CandleStore()


class CandleEngine:

    def __init__(self, symbol="BTCUSDT", timeframe="1m"):

        self.symbol = symbol

        self.timeframe = timeframe

        self.timeframe_seconds = TIMEFRAMES[timeframe]

        self.current_candle = None

    def process_tick(self, tick):

        tick_time = tick.timestamp // 1000

        candle_open_time = (
            tick_time // self.timeframe_seconds
        ) * self.timeframe_seconds

        candle_close_time = (
            candle_open_time + self.timeframe_seconds
        )

        # FIRST CANDLE
        if self.current_candle is None:

            self.current_candle = CandleEvent(
                symbol=tick.symbol,
                timeframe=self.timeframe,

                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,

                volume=tick.quantity,

                open_time=candle_open_time,
                close_time=candle_close_time,

                is_closed=False
            )

            return

        # NEW CANDLE STARTS
        if tick_time >= self.current_candle.close_time:

            self.current_candle.is_closed = True

            candle_queue.put(self.current_candle)

            candle_store.add_candle(
                tick.symbol,
                self.timeframe,
                self.current_candle
            )

            SystemState.total_candles_processed += 1

            candle_logger.info(
                f"Candle closed: "
                f"{self.current_candle.symbol} "
                f"{self.current_candle.timeframe} "
                f"C={self.current_candle.close}"
            )

            self.current_candle = CandleEvent(
                symbol=tick.symbol,
                timeframe=self.timeframe,

                open=tick.price,
                high=tick.price,
                low=tick.price,
                close=tick.price,

                volume=tick.quantity,

                open_time=candle_open_time,
                close_time=candle_close_time,

                is_closed=False
            )

            return

        # UPDATE CURRENT CANDLE

        self.current_candle.high = max(
            self.current_candle.high,
            tick.price
        )

        self.current_candle.low = min(
            self.current_candle.low,
            tick.price
        )

        self.current_candle.close = tick.price

        self.current_candle.volume += tick.quantity


def start_candle_engine():

    engine = CandleEngine()

    while True:

        tick = tick_queue.get()

        engine.process_tick(tick)