from decimal import Decimal


class VolatilityEngine:

    def calculate_volatility(
        self,
        candle
    ):

        high = Decimal(
            str(candle.high)
        )

        low = Decimal(
            str(candle.low)
        )

        close = Decimal(
            str(candle.close)
        )

        if close == 0:

            return Decimal("0")

        volatility = (
            (high - low)
            / close
        )

        return volatility