from portfolio.models.trade import (
    Trade,
)


class PerformanceAnalyzer:

    def calculate_winrate(
        self,
        trades: list[Trade],
    ) -> float:

        if not trades:
            return 0.0

        wins = sum(
            1
            for trade in trades
            if trade.realized_pnl > 0
        )

        return (
            wins / len(trades)
        ) * 100

    def calculate_total_pnl(
        self,
        trades: list[Trade],
    ) -> float:

        return sum(
            trade.realized_pnl
            for trade in trades
        )

    def calculate_profit_factor(
        self,
        trades: list[Trade],
    ) -> float:

        gross_profit = sum(
            trade.realized_pnl
            for trade in trades
            if trade.realized_pnl > 0
        )

        gross_loss = abs(sum(
            trade.realized_pnl
            for trade in trades
            if trade.realized_pnl < 0
        ))

        if gross_loss == 0:
            return float("inf")

        return (
            gross_profit
            / gross_loss
        )