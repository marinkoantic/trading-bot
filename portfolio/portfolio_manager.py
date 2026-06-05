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
        execution_report,
    ) -> None:

        position = Position(
            symbol=(
                execution_report.symbol
            ),

            quantity=(
                execution_report.quantity
            ),

            entry_price=(
                execution_report.executed_price
            ),

            current_price=(
                execution_report.executed_price
            ),

            side=execution_report.side,
        )

        self.positions[
            execution_report.symbol
        ] = position

        print(
            f"[PORTFOLIO] "
            f"Opened "
            f"{execution_report.side} "
            f"{execution_report.symbol}"
        )

        print(
            f"[PORTFOLIO] "
            f"Fill="
            f"{execution_report.executed_price:.8f}"
        )

        print(
            f"[PORTFOLIO] "
            f"Fee="
            f"{execution_report.fee:.6f}"
        )

        print(
            f"[PORTFOLIO] "
            f"Slippage="
            f"{execution_report.slippage:.6f}"
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