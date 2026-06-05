from dataclasses import dataclass


@dataclass(slots=True)
class Position:

    symbol: str

    quantity: float

    entry_price: float

    current_price: float

    side: str

    @property
    def unrealized_pnl(self) -> float:

        if self.side == "LONG":

            return (
                self.current_price
                - self.entry_price
            ) * self.quantity

        return (
            self.entry_price
            - self.current_price
        ) * self.quantity

    @property
    def exposure(self) -> float:

        return (
            self.quantity
            * self.current_price
        )