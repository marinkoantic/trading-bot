import random

from market.market_state import (
    MarketState,
)

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
        quantity: float,
    ) -> ExecutionReport:

        snapshot = (
            MarketState.get_snapshot()
        )

        if snapshot is None:

            raise RuntimeError(
                "No market snapshot available"
            )

        slippage_pct = random.uniform(
            0,
            self.max_slippage_pct,
        )

        if side == "LONG":

            base_price = snapshot.ask

            executed_price = (
                base_price
                * (
                    1 + slippage_pct
                )
            )

        else:

            base_price = snapshot.bid

            executed_price = (
                base_price
                * (
                    1 - slippage_pct
                )
            )

        slippage = (
            executed_price
            - base_price
        ) * quantity

        fee = (
            executed_price
            * quantity
            * self.fee_rate
        )

        return ExecutionReport(
            symbol=symbol,

            side=side,

            requested_price=base_price,

            executed_price=executed_price,

            quantity=quantity,

            slippage=slippage,

            fee=fee,
        )