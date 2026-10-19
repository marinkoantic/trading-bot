from portfolio.models.trade import (
    Trade,
)


class EquityCurve:

    def build_curve(
        self,
        trades: list[Trade],
        starting_balance: float = 1000,
    ) -> list[float]:

        equity = starting_balance

        curve = [equity]

        for trade in trades:

            equity += (
                trade.realized_pnl
            )

            curve.append(equity)

        return curve

    def max_drawdown(
        self,
        curve: list[float],
    ) -> float:

        peak = curve[0]

        max_dd = 0.0

        for value in curve:

            if value > peak:

                peak = value

            drawdown = (
                peak - value
            ) / peak

            if drawdown > max_dd:

                max_dd = drawdown

        return max_dd * 100