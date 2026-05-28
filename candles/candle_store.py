from collections import defaultdict


class CandleStore:

    def __init__(self):

        self.candles = defaultdict(list)

    def add_candle(self, symbol, timeframe, candle):

        key = f"{symbol}_{timeframe}"

        self.candles[key].append(candle)

    def get_candles(self, symbol, timeframe):

        key = f"{symbol}_{timeframe}"

        return self.candles[key]

    def get_latest_candle(self, symbol, timeframe):

        candles = self.get_candles(symbol, timeframe)

        if candles:
            return candles[-1]

        return None