import time

from core.models import SignalEvent
from core.events import candle_queue

from indicators.indicator_engine import (
    indicator_cache
)

from strategy.filter_layer import (
    FilterLayer
)

from strategy.signal_router import (
    SignalRouter
)

from utils.logger import setup_logger


signal_logger = setup_logger(
    "signal_logger",
    "logs/signals/signals.log"
)

decision_logger = setup_logger(
    "decision_logger",
    "logs/decisions/decisions.log"
)


filter_layer = FilterLayer()

signal_router = SignalRouter()


class StrategyEngine:

    def process_candle(self, candle):

        ema_20 = indicator_cache.get_value(
            candle.symbol,
            candle.timeframe,
            "ema_20"
        )

        ema_50 = indicator_cache.get_value(
            candle.symbol,
            candle.timeframe,
            "ema_50"
        )

        rsi_14 = indicator_cache.get_value(
            candle.symbol,
            candle.timeframe,
            "rsi_14"
        )

        # WAIT UNTIL INDICATORS READY
        if (
            ema_20 is None or
            ema_50 is None or
            rsi_14 is None
        ):
            return

        # COOLDOWN FILTER
        if filter_layer.cooldown_active(
            candle.symbol
        ):

            decision_logger.info(
                f"{candle.symbol} signal blocked "
                f"by cooldown filter"
            )

            return

        signal = None

        # LONG SIGNAL
        if (
            ema_20 > ema_50 and
            rsi_14 > 55
        ):

            signal = SignalEvent(
                symbol=candle.symbol,

                signal_type="LONG",

                confidence=0.75,

                price=candle.close,

                timestamp=int(time.time()),

                strategy_name=(
                    "EMA_RSI_STRATEGY"
                ),

                reason=(
                    "EMA20 above EMA50 "
                    "and RSI above 55"
                )
            )

        # SHORT SIGNAL
        elif (
            ema_20 < ema_50 and
            rsi_14 < 45
        ):

            signal = SignalEvent(
                symbol=candle.symbol,

                signal_type="SHORT",

                confidence=0.75,

                price=candle.close,

                timestamp=int(time.time()),

                strategy_name=(
                    "EMA_RSI_STRATEGY"
                ),

                reason=(
                    "EMA20 below EMA50 "
                    "and RSI below 45"
                )
            )

        # NO SIGNAL
        else:

            decision_logger.info(
                f"{candle.symbol} "
                f"no signal generated"
            )

            return

        filter_layer.update_signal_time(
            candle.symbol
        )

        signal_router.route_signal(signal)

        signal_logger.info(
            f"{signal.symbol} "
            f"{signal.signal_type} "
            f"{signal.reason}"
        )


def start_strategy_engine():

    engine = StrategyEngine()

    while True:

        candle = candle_queue.get()

        engine.process_candle(candle)