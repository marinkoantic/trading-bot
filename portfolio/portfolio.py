from core.models import PositionEvent
from core.events import fill_queue

from portfolio.pnl import (
    calculate_realized_pnl
)

from portfolio.exposure import ExposureTracker
from portfolio.risk_manager import RiskManager

from analytics.analytics_engine import AnalyticsEngine
from analytics.snapshot_manager import SnapshotManager

from utils.logger import setup_logger


position_logger = setup_logger(
    "position_logger",
    "logs/positions/positions.log"
)


exposure_tracker = ExposureTracker()

risk_manager = RiskManager()

analytics_engine = AnalyticsEngine()

snapshot_manager = SnapshotManager()


class PortfolioEngine:

    def __init__(self):

        self.balance = 10000

        self.open_positions = {}

        self.trade_history = []

        self.restore_snapshot()

    def restore_snapshot(self):

        snapshot = (
            snapshot_manager.load_snapshot()
        )

        if snapshot is None:
            return

        self.balance = snapshot.get(
            "balance",
            10000
        )

        position_logger.info(
            "Runtime snapshot restored"
        )

    def process_fill(self, fill_event):

        symbol = "BTCUSDT"

        position_side = "LONG"

        position_value = (
            fill_event.fill_price *
            fill_event.filled_quantity
        )

        # RISK CHECK
        if not risk_manager.can_open_position(
            self.open_positions
        ):

            position_logger.warning(
                "Max open positions reached"
            )

            return

        # OPEN POSITION
        if symbol not in self.open_positions:

            position = PositionEvent(
                symbol=symbol,

                side=position_side,

                entry_price=fill_event.fill_price,

                current_price=fill_event.fill_price,

                quantity=fill_event.filled_quantity,

                unrealized_pnl=0,

                realized_pnl=0,

                timestamp=fill_event.timestamp
            )

            self.open_positions[symbol] = position

            exposure_tracker.update_exposure(
                position_value
            )

            self.balance -= (
                position_value + fill_event.fee
            )

            position_logger.info(
                f"Opened {symbol} "
                f"at {fill_event.fill_price}"
            )

            snapshot_manager.save_snapshot(self)

            analytics_engine.process_portfolio(self)

            return

        # CLOSE POSITION
        existing_position = self.open_positions[symbol]

        realized_pnl = calculate_realized_pnl(
            existing_position.entry_price,
            fill_event.fill_price,
            existing_position.quantity,
            existing_position.side
        )

        self.balance += (
            position_value +
            realized_pnl -
            fill_event.fee
        )

        existing_position.realized_pnl = realized_pnl

        self.trade_history.append(
            existing_position
        )

        del self.open_positions[symbol]

        position_logger.info(
            f"Closed {symbol} "
            f"PnL={realized_pnl}"
        )

        snapshot_manager.save_snapshot(self)

        analytics_engine.process_portfolio(self)


def start_portfolio_engine():

    engine = PortfolioEngine()

    while True:

        fill_event = fill_queue.get()

        engine.process_fill(fill_event)