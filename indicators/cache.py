from collections import defaultdict


class IndicatorCache:

    def __init__(self):

        self.cache = defaultdict(dict)

    def set_value(
        self,
        symbol,
        timeframe,
        key,
        value
    ):

        cache_key = (
            f"{symbol}_{timeframe}"
        )

        self.cache[cache_key][key] = value

    def get_value(
        self,
        symbol,
        timeframe,
        key
    ):

        cache_key = (
            f"{symbol}_{timeframe}"
        )

        return self.cache[
            cache_key
        ].get(key)