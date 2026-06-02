from decimal import Decimal

from config.settings import (
    TRADING_SYMBOL
)

EXCHANGE_RULES = {

    TRADING_SYMBOL: {

        "tick_size": Decimal(
            "0.00000001"
        ),

        "step_size": Decimal(
            "1"
        ),

        "min_qty": Decimal(
            "1"
        ),

        "min_notional": Decimal(
            "5"
        )
    }
}