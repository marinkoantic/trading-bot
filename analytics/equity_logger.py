import json
import time

from portfolio.account_state import (
    account_state
)


class EquityLogger:

    def __init__(self):

        self.file_path = (
            "logs/analytics/equity_curve.jsonl"
        )

    def log_equity(self):

        snapshot = {

            "timestamp": int(time.time()),

            "balance": (
                account_state.balance
            ),

            "equity": (
                account_state.get_equity()
            ),

            "realized_pnl": (
                account_state.realized_pnl
            ),

            "unrealized_pnl": (
                account_state.unrealized_pnl
            ),

            "fees": (
                account_state.total_fees
            )
        }

        with open(
            self.file_path,
            "a"
        ) as file:

            file.write(
                json.dumps(snapshot)
                + "\n"
            )