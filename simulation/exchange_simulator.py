from core.models import FillEvent

from simulation.fees import (
    calculate_fee
)

from simulation.slippage import (
    apply_slippage
)

from simulation.latency import (
    simulate_latency
)

from simulation.fills import (
    simulate_fill
)


class ExchangeSimulator:

    def execute_order(self, order):

        latency_ms = simulate_latency()

        filled_quantity, is_partial = (
            simulate_fill(
                order.quantity
            )
        )

        fill_price = apply_slippage(
            order.price,
            order.side
        )

        notional = (
            fill_price *
            filled_quantity
        )

        fee = calculate_fee(
            notional
        )

        fill_event = FillEvent(
            order_id=order.order_id,

            filled_quantity=filled_quantity,

            fill_price=fill_price,

            fee=fee,

            slippage=abs(
                fill_price - order.price
            ),

            timestamp=order.timestamp,

            is_partial=is_partial
        )

        return fill_event