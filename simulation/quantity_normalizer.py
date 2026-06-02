from decimal import Decimal
from decimal import ROUND_DOWN

from simulation.exchange_rules import (
    EXCHANGE_RULES
)


def normalize_quantity(
    symbol,
    quantity
):

    step_size = (
        EXCHANGE_RULES[symbol][
            "step_size"
        ]
    )

    return Decimal(
        str(quantity)
    ).quantize(
        step_size,
        rounding=ROUND_DOWN
    )