import json


class ReplayEngine:

    def __init__(self):

        self.trade_log_path = (
            "storage/jsonl/trades.jsonl"
        )

    def load_trades(self):

        trades = []

        try:

            with open(
                self.trade_log_path,
                "r"
            ) as file:

                for line in file:

                    trades.append(
                        json.loads(line)
                    )

        except FileNotFoundError:

            return []

        return trades