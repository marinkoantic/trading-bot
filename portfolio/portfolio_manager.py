from portfolio.models.position import (
    Position,
)

from portfolio.models.trade import (
    Trade,
)

from analytics.performance_analyzer import (
    PerformanceAnalyzer,
)

from analytics.equity_curve import (
    EquityCurve,
)


class PortfolioManager:

    def __init__(self):

        self.positions: dict[
            str,
            Position
        ] = {}

        self.closed_trades: list[
            Trade
        ] = []

        self.performance_analyzer = (
            PerformanceAnalyzer()
        )

        self.equity_curve = (
            EquityCurve()
        )

    def has_position(
        self,
        symbol: str,
    ) -> bool:

        return symbol in self.positions

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

    def close_position(
        self,
        execution_report,
    ) -> None:

        position = self.positions.get(
            execution_report.symbol
        )

        if not position:

            print(
                "[PORTFOLIO] "
                "No open position"
            )

            return

        if position.side == "LONG":

            realized_pnl = (
                execution_report.executed_price
                - position.entry_price
            ) * position.quantity

        else:

            realized_pnl = (
                position.entry_price
                - execution_report.executed_price
            ) * position.quantity

        realized_pnl -= (
            execution_report.fee
        )

        trade = Trade(
            symbol=position.symbol,

            side=position.side,

            quantity=position.quantity,

            entry_price=(
                position.entry_price
            ),

            exit_price=(
                execution_report.executed_price
            ),

            realized_pnl=realized_pnl,

            fee=execution_report.fee,
        )

        self.closed_trades.append(
            trade
        )

        del self.positions[
            execution_report.symbol
        ]

        print(
            f"[PORTFOLIO] "
            f"Closed "
            f"{position.symbol}"
        )

        print(
            f"[PORTFOLIO] "
            f"ExitPrice="
            f"{execution_report.executed_price:.8f}"
        )

        print(
            f"[PORTFOLIO] "
            f"RealizedPnL="
            f"{realized_pnl:.6f}"
        )

        self.print_performance_summary()

    def update_market_price(
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

        if position.side == "LONG":

            pnl = (
                price
                - position.entry_price
            ) * position.quantity

        else:

            pnl = (
                position.entry_price
                - price
            ) * position.quantity

        print(
            f"[PORTFOLIO] "
            f"PnL={pnl:.6f}"
        )

    def print_performance_summary(
        self,
    ) -> None:

        trades = self.closed_trades

        if not trades:
            return

        total_pnl = (
            self.performance_analyzer
            .calculate_total_pnl(
                trades
            )
        )

        winrate = (
            self.performance_analyzer
            .calculate_winrate(
                trades
            )
        )

        profit_factor = (
            self.performance_analyzer
            .calculate_profit_factor(
                trades
            )
        )

        curve = (
            self.equity_curve
            .build_curve(
                trades
            )
        )

        max_drawdown = (
            self.equity_curve
            .max_drawdown(curve)
        )

        print("\n==========")
        print("PERFORMANCE")
        print("==========")

        print(
            f"Trades: {len(trades)}"
        )

        print(
            f"TotalPnL: "
            f"{total_pnl:.6f}"
        )

        print(
            f"Winrate: "
            f"{winrate:.2f}%"
        )

        print(
            f"ProfitFactor: "
            f"{profit_factor:.2f}"
        )

        print(
            f"MaxDrawdown: "
            f"{max_drawdown:.2f}%"
        )

        print("==========\n")