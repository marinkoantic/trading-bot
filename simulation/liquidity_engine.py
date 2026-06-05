import random


class LiquidityEngine:

    def __init__(self):

        self.min_liquidity = 250_000

        self.max_liquidity = 5_000_000

    def get_available_liquidity(
        self,
        symbol: str,
    ) -> float:

        return random.uniform(
            self.min_liquidity,
            self.max_liquidity,
        )

    def calculate_fill_quantity(
        self,
        requested_quantity: float,
        available_liquidity: float,
    ) -> float:

        return min(
            requested_quantity,
            available_liquidity,
        )