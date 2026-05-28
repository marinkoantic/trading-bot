from core.events import candle_queue
from candles.candle_engine import candle_store

from indicators.ema import calculate_ema
from indicators.rsi import calculate_rsi
from indicators.cache import IndicatorCache

from utils.logger import setup_logger

indicator_logger = setup_logger(
    "indicator_logger",
    "logs/system/indicators.log"
)

indicator_cache = IndicatorCache()

class IndicatorEngine:
    def process_candle(self, candle):
        candles = candle_store.get_candles(
            candle.symbol,
            candle.timeframe
        )
        
        closes = [c.close for c in candles]

        ema_20 = calculate_ema(closes, 20)

        ema_50 = calculate_ema(closes, 50)

        rsi_14 = calculate_rsi(closes, 14)

        indicator_cache.set_value(
            candle.symbol,
            candle.timeframe,
            "ema_20",
            ema_20
        )

        indicator_cache.set_value(
            candle.symbol,
            candle.timeframe,
            "ema_50",
            ema_50
        )

        indicator_cache.set_value(
            candle.symbol,
            candle.timeframe,
            "rsi_14",
            rsi_14
        )

        indicator_logger.info(
            f"{candle.symbol} "
            f"EMA20={ema_20} "
            f"EMA50={ema_50} "
            f"RSI14={rsi_14}"
        )
        
def start_indicator_engine():
    engine = IndicatorEngine()
    while True:
        candle = candle_queue.get()
        engine.process_candle(candle)