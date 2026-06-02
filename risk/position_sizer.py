from decimal import Decimal

from config.settings import (
    MAX_POSITION_SIZE
)

from simulation.exchange_rules import (
    EXCHANGE_RULES
)


class PositionSizer:

    def calculate_position_size(
        self,
        symbol,
        portfolio_balance,
        entry_price,
        risk_percent=1
    ):

        portfolio_balance = Decimal(
            str(portfolio_balance)
        )

        entry_price = Decimal(
            str(entry_price)
        )

        risk_percent = Decimal(
            str(risk_percent)
        )

        risk_amount = (
            portfolio_balance
            * (risk_percent / 100)
        )

        quantity = (
            risk_amount
            / entry_price
        )

        # MIN NOTIONAL CHECK
        min_notional = Decimal(
            str(
                EXCHANGE_RULES[
                    symbol
                ][
                    "min_notional"
                ]
            )
        )

        current_notional = (
            quantity
            * entry_price
        )

        if current_notional < min_notional:

            quantity = (
                min_notional
                / entry_price
            )

        # MAX POSITION LIMIT
        if quantity > Decimal(
            str(MAX_POSITION_SIZE)
        ):

            quantity = Decimal(
                str(MAX_POSITION_SIZE)
            )

        return float(quantity)