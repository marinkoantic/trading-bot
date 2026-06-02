from decimal import Decimal
from decimal import ROUND_DOWN

from simulation.exchange_rules import (
    EXCHANGE_RULES
)


def normalize_price(
    symbol,
    price
):

    tick_size = (
        EXCHANGE_RULES[symbol][
            "tick_size"
        ]
    )

    return Decimal(
        str(price)
    ).quantize(
        tick_size,
        rounding=ROUND_DOWN
    )