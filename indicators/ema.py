def calculate_ema(prices, period):

    if len(prices) < period:
        return None

    multiplier = 2 / (period + 1)

    ema = sum(prices[:period]) / period

    for price in prices[period:]:

        ema = ((price - ema) * multiplier) + ema

    return ema