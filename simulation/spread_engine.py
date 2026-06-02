from decimal import Decimal


class SpreadEngine:

    def calculate_spread(
        self,
        symbol,
        price
    ):

        price = Decimal(
            str(price)
        )

        # BASE SPREAD
        spread_percent = Decimal(
            "0.0005"
        )

        spread = (
            price * spread_percent
        )

        return spread

    def apply_market_spread(
        self,
        symbol,
        side,
        price
    ):

        price = Decimal(
            str(price)
        )

        spread = self.calculate_spread(
            symbol,
            price
        )

        # BUY = WORSE PRICE
        if side == "BUY":

            return price + spread

        # SELL = WORSE PRICE
        return price - spread