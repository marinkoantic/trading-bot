from portfolio.models.position import (
    Position,
)


class PortfolioManager:

    def __init__(self):

        self.positions: dict[
            str,
            Position
        ] = {}

    def open_position(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        side: str = "LONG",
    ) -> None:

        position = Position(
            symbol=symbol,

            quantity=quantity,

            entry_price=entry_price,

            current_price=entry_price,

            side=side,
        )

        self.positions[symbol] = (
            position
        )

        print(
            f"[PORTFOLIO] "
            f"Opened {side} "
            f"{symbol}"
        )

    def update_price(
        self,
        symbol: str,
        price: float,
    ) -> None:

        position = self.positions.get(
            symbol
        )

        if not position:
            return

        position.current_price = price

        print(
            f"[PORTFOLIO] "
            f"PnL="
            f"{position.unrealized_pnl:.6f}"
        )

    def has_position(
        self,
        symbol: str,
    ) -> bool:

        return symbol in self.positions