from decimal import Decimal


class LiquidityEngine:

    def calculate_fill_ratio(
        self,
        symbol,
        quantity
    ):

        quantity = Decimal(
            str(quantity)
        )

        # SIMULATED LUNC LIQUIDITY

        if quantity <= Decimal("1000"):

            return Decimal("1.0")

        if quantity <= Decimal("5000"):

            return Decimal("0.85")

        if quantity <= Decimal("10000"):

            return Decimal("0.65")

        return Decimal("0.40")