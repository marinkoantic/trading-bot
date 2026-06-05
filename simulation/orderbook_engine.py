import random

from dataclasses import (
    dataclass,
)


@dataclass(slots=True)
class OrderBookLevel:

    price: float

    quantity: float


class OrderBookEngine:

    def build_ask_levels(
        self,
        ask_price: float,
    ) -> list[OrderBookLevel]:

        levels = []

        for i in range(5):

            price = (
                ask_price
                * (
                    1 + (i * 0.0002)
                )
            )

            quantity = random.uniform(
                100_000,
                2_000_000,
            )

            levels.append(
                OrderBookLevel(
                    price=price,

                    quantity=quantity,
                )
            )

        return levels

    def build_bid_levels(
        self,
        bid_price: float,
    ) -> list[OrderBookLevel]:

        levels = []

        for i in range(5):

            price = (
                bid_price
                * (
                    1 - (i * 0.0002)
                )
            )

            quantity = random.uniform(
                100_000,
                2_000_000,
            )

            levels.append(
                OrderBookLevel(
                    price=price,

                    quantity=quantity,
                )
            )

        return levels