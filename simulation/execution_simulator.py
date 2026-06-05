import random

from simulation.models.execution_report import (
    ExecutionReport,
)


class ExecutionSimulator:

    def __init__(self):

        self.fee_rate = 0.001

        self.max_slippage_pct = 0.0015

    def execute_market_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
    ) -> ExecutionReport:

        slippage_pct = random.uniform(
            0,
            self.max_slippage_pct,
        )

        if side == "LONG":

            executed_price = (
                price * (
                    1 + slippage_pct
                )
            )

        else:

            executed_price = (
                price * (
                    1 - slippage_pct
                )
            )

        slippage = (
            executed_price - price
        ) * quantity

        fee = (
            executed_price
            * quantity
            * self.fee_rate
        )

        return ExecutionReport(
            symbol=symbol,

            side=side,

            requested_price=price,

            executed_price=executed_price,

            quantity=quantity,

            slippage=slippage,

            fee=fee,
        )