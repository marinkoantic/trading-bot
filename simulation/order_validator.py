from decimal import Decimal

from simulation.exchange_rules import (
    EXCHANGE_RULES
)


class OrderValidator:

    def validate_order(
        self,
        symbol,
        price,
        quantity
    ):

        rules = EXCHANGE_RULES[symbol]

        notional = (
            Decimal(str(price))
            * Decimal(str(quantity))
        )

        if notional < rules["min_notional"]:

            return (
                False,
                "MIN_NOTIONAL_FAILED"
            )

        if Decimal(str(quantity)) < rules["min_qty"]:

            return (
                False,
                "MIN_QTY_FAILED"
            )

        return (
            True,
            "VALID"
        )