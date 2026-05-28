import json
import os


class TradeLogger:

    def __init__(self):

        os.makedirs(
            "storage/jsonl",
            exist_ok=True
        )

        self.trade_log_path = (
            "storage/jsonl/trades.jsonl"
        )

    def log_trade(self, trade):

        trade_data = {
            "symbol": trade.symbol,
            "side": trade.side,
            "entry_price": trade.entry_price,
            "current_price": trade.current_price,
            "quantity": trade.quantity,
            "realized_pnl": trade.realized_pnl,
            "timestamp": trade.timestamp
        }

        with open(
            self.trade_log_path,
            "a"
        ) as file:

            file.write(
                json.dumps(trade_data) + "\n"
            )