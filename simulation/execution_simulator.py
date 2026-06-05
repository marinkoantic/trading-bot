import random

from market.market_state import (
    MarketState,
)

from simulation.liquidity_engine import (
    LiquidityEngine,
)

from simulation.models.execution_report import (
    ExecutionReport,
)


class ExecutionSimulator:

    def __init__(self):

        self.fee_rate = 0.001

        self.max_slippage_pct = 0.0015

        self.liquidity_engine = (
            LiquidityEngine()
        )

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

        available_liquidity = (
            self.liquidity_engine
            .get_available_liquidity(
                symbol
            )
        )

        filled_quantity = (
            self.liquidity_engine
            .calculate_fill_quantity(
                requested_quantity=quantity,

                available_liquidity=(
                    available_liquidity
                ),
            )
        )

        partial_fill = (
            filled_quantity
            < quantity
        )

        liquidity_ratio = (
            quantity
            / available_liquidity
        )

        impact_multiplier = max(
            1.0,
            liquidity_ratio,
        )

        slippage_pct = random.uniform(
            0,
            self.max_slippage_pct,
        ) * impact_multiplier

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
        ) * filled_quantity

        fee = (
            executed_price
            * filled_quantity
            * self.fee_rate
        )

        print(
            f"[LIQUIDITY] "
            f"Available="
            f"{available_liquidity:,.0f}"
        )

        if partial_fill:

            print(
                f"[LIQUIDITY] "
                f"Partial fill "
                f"{filled_quantity:,.0f}/"
                f"{quantity:,.0f}"
            )

        return ExecutionReport(
            symbol=symbol,

            side=side,

            requested_price=base_price,

            executed_price=executed_price,

            quantity=filled_quantity,

            slippage=slippage,

            fee=fee,
        )