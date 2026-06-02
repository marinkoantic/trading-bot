import requests

from core.models import CandleEvent

from candles.candle_engine import (
    candle_store
)

from utils.logger import setup_logger


historical_logger = setup_logger(
    "historical_logger",
    "logs/system/historical.log"
)


BINANCE_KLINES_URL = (
    "https://api.binance.com/api/v3/klines"
)


class HistoricalLoader:

    def load_historical_candles(
        self,
        symbol="LUNCUSDT",
        interval="1m",
        limit=200
    ):

        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }

        response = requests.get(
            BINANCE_KLINES_URL,
            params=params,
            timeout=10
        )

        if response.status_code != 200:

            historical_logger.error(
                f"Failed loading candles: "
                f"{response.text}"
            )

            return 0

        data = response.json()

        loaded = 0

        for candle_data in data:

            candle = CandleEvent(
                symbol=symbol,

                timeframe=interval,

                open=float(candle_data[1]),

                high=float(candle_data[2]),

                low=float(candle_data[3]),

                close=float(candle_data[4]),

                volume=float(candle_data[5]),

                open_time=int(candle_data[0]),

                close_time=int(candle_data[6]),
                
                is_closed=True
            )

            candle_store.add_candle(
                symbol,
                interval,
                candle
            )

            loaded += 1

        historical_logger.info(
            f"Loaded {loaded} historical candles "
            f"for {symbol}"
        )

        return loaded