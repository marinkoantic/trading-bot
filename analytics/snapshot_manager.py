import json
import os


class SnapshotManager:

    def __init__(self):

        os.makedirs(
            "storage/snapshots",
            exist_ok=True
        )

        self.snapshot_path = (
            "storage/snapshots/runtime_snapshot.json"
        )

    def serialize_position(self, position):

        return {
            "symbol": position.symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "current_price": position.current_price,
            "quantity": position.quantity,
            "unrealized_pnl": (
                position.unrealized_pnl
            ),
            "realized_pnl": (
                position.realized_pnl
            ),
            "timestamp": position.timestamp
        }

    def save_snapshot(self, portfolio_engine):

        snapshot = {
            "balance": portfolio_engine.balance,

            "open_positions": {

                symbol: self.serialize_position(
                    position
                )

                for symbol, position
                in portfolio_engine.open_positions.items()
            },

            "trade_count": len(
                portfolio_engine.trade_history
            )
        }

        with open(
            self.snapshot_path,
            "w"
        ) as file:

            json.dump(
                snapshot,
                file,
                indent=4
            )

    def load_snapshot(self):

        if not os.path.exists(
            self.snapshot_path
        ):

            return None

        with open(
            self.snapshot_path,
            "r"
        ) as file:

            return json.load(file)