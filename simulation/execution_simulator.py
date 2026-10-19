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

from simulation.orderbook_engine import (
    OrderBookEngine,
)


class ExecutionSimulator:

    def __init__(self):

        self.fee_rate = 0.001

        # 0.15% max base slippage
        self.max_slippage_pct = 0.0015

        self.orderbook_engine = (
            OrderBookEngine()
        )

        self.liquidity_engine = (
            LiquidityEngine()
        )

    def execute_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
    ) -> ExecutionReport:

        print(
            "[DEBUG] execute_market_order called"
        )

        snapshot = (
            MarketState.get_snapshot()
        )

        print(
            f"[DEBUG] Snapshot="
            f"{snapshot}"
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

        print(
            f"[DEBUG] Available liquidity="
            f"{available_liquidity}"
        )

        if available_liquidity <= 0:

            raise RuntimeError(
                "No liquidity available"
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

        print(
            f"[DEBUG] Filled quantity="
            f"{filled_quantity}"
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

        print(
            f"[DEBUG] Slippage pct="
            f"{slippage_pct}"
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

        spread_cost = (
            snapshot.ask
            - snapshot.bid
        ) * filled_quantity

        slippage = abs(
            executed_price
            - base_price
        ) * filled_quantity

        fee = (
            executed_price
            * filled_quantity
            * self.fee_rate
        )

        total_transaction_cost = (
            fee
            + slippage
            + spread_cost
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

        print(
            f"[EXECUTION] "
            f"SpreadCost="
            f"{spread_cost:.6f}"
        )

        print(
            f"[EXECUTION] "
            f"TransactionCost="
            f"{total_transaction_cost:.6f}"
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

    def calculate_vwap_fill(
        self,
        levels,
        quantity,
    ):

        remaining = quantity

        total_cost = 0.0

        filled = 0.0

        for level in levels:

            if remaining <= 0:

                break

            fill_qty = min(
                remaining,
                level.quantity,
            )

            total_cost += (
                fill_qty
                * level.price
            )

            filled += fill_qty

            remaining -= fill_qty

        if filled == 0:

            raise RuntimeError(
                "No liquidity available"
            )

        vwap_price = (
            total_cost
            / filled
        )

        return (
            vwap_price,
            filled,
        )