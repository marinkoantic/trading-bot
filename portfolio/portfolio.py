from core.models import PositionEvent
from core.events import fill_queue

from portfolio.exposure import (
    ExposureTracker
)

from portfolio.risk_manager import (
    RiskManager
)

from portfolio.pnl import (
    calculate_realized_pnl
)

from analytics.equity_logger import (
    EquityLogger
)

from portfolio.account_state import (
    account_state
)

from portfolio.valuation_engine import (
    ValuationEngine
)

from analytics.analytics_engine import (
    AnalyticsEngine
)

from analytics.snapshot_manager import (
    SnapshotManager
)

from candles.candle_engine import (
    candle_store
)

from config.settings import (
    TRADING_TIMEFRAME
)

from utils.logger import (
    setup_logger
)


position_logger = setup_logger(
    "position_logger",
    "logs/positions/positions.log"
)


exposure_tracker = (
    ExposureTracker()
)

risk_manager = (
    RiskManager()
)

analytics_engine = (
    AnalyticsEngine()
)

snapshot_manager = (
    SnapshotManager()
)

valuation_engine = (
    ValuationEngine()
)

equity_logger = (
    EquityLogger()
)


class PortfolioEngine:

    def __init__(self):

        self.open_positions = {}

        self.trade_history = []

        self.restore_snapshot()

    # =====================================================
    # SNAPSHOT RESTORE
    # =====================================================

    def restore_snapshot(self):

        snapshot = (
            snapshot_manager.load_snapshot()
        )

        if snapshot is None:

            return

        # ============================================
        # ACCOUNT STATE RESTORE
        # ============================================

        account_state.balance = (
            snapshot.get(
                "balance",
                account_state.balance
            )
        )

        account_state.realized_pnl = (
            snapshot.get(
                "realized_pnl",
                0.0
            )
        )

        account_state.unrealized_pnl = (
            snapshot.get(
                "unrealized_pnl",
                0.0
            )
        )

        account_state.total_fees = (
            snapshot.get(
                "total_fees",
                0.0
            )
        )

        # ============================================
        # OPEN POSITIONS RESTORE
        # ============================================

        open_positions = (
            snapshot.get(
                "open_positions",
                {}
            )
        )

        for symbol, data in (
            open_positions.items()
        ):

            restored_position = PositionEvent(

                symbol=data["symbol"],

                side=data["side"],

                entry_price=data["entry_price"],

                current_price=data["current_price"],

                quantity=data["quantity"],

                unrealized_pnl=data["unrealized_pnl"],

                realized_pnl=data["realized_pnl"],

                timestamp=data["timestamp"]
            )

            self.open_positions[
                symbol
            ] = restored_position

        position_logger.info(
            f"Runtime snapshot restored | "
            f"POSITIONS={len(self.open_positions)}"
        )

    # =====================================================
    # UNREALIZED PNL
    # =====================================================

    def update_unrealized_pnl(self):

        total_unrealized = 0

        for symbol, position in (
            self.open_positions.items()
        ):

            candles = candle_store.get_candles(
                symbol,
                TRADING_TIMEFRAME
            )

            if not candles:

                continue

            latest_price = (
                candles[-1].close
            )

            unrealized_pnl = (
                valuation_engine
                .calculate_unrealized_pnl(
                    position.entry_price,
                    latest_price,
                    position.quantity,
                    position.side
                )
            )

            position.current_price = (
                latest_price
            )

            position.unrealized_pnl = (
                unrealized_pnl
            )

            total_unrealized += (
                unrealized_pnl
            )

        account_state.unrealized_pnl = (
            total_unrealized
        )

    # =====================================================
    # OPEN POSITION
    # =====================================================

    def open_position(
        self,
        fill_event,
        position_side
    ):

        symbol = fill_event.symbol

        position_value = (
            fill_event.fill_price
            * fill_event.filled_quantity
        )

        # RISK CHECK
        if not risk_manager.can_open_position(
            self.open_positions
        ):

            position_logger.warning(
                "Max open positions reached"
            )

            return

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

        self.open_positions[
            symbol
        ] = position

        exposure_tracker.update_exposure(
            position_value
        )

        # LONG bezahlt Kapital
        if position_side == "LONG":

            account_state.balance -= (
                position_value
            )

        position_logger.info(
            f"OPENED | "
            f"{symbol} | "
            f"SIDE={position_side} | "
            f"ENTRY={fill_event.fill_price} | "
            f"QTY={fill_event.filled_quantity}"
        )

        self.update_unrealized_pnl()

        equity_logger.log_equity()

        snapshot_manager.save_snapshot(
            self
        )

        analytics_engine.process_portfolio(
            self
        )

    # =====================================================
    # CLOSE POSITION
    # =====================================================

    def close_position(
        self,
        existing_position,
        fill_event
    ):

        symbol = fill_event.symbol

        position_value = (
            fill_event.fill_price
            * existing_position.quantity
        )

        realized_pnl = (
            calculate_realized_pnl(
                existing_position.entry_price,
                fill_event.fill_price,
                existing_position.quantity,
                existing_position.side
            )
        )

        existing_position.realized_pnl = (
            realized_pnl
        )

        account_state.apply_realized_pnl(
            realized_pnl
        )

        # LONG bekommt Kapital zurück
        if existing_position.side == "LONG":

            account_state.balance += (
                position_value
            )

        self.trade_history.append(
            existing_position
        )

        del self.open_positions[symbol]

        position_logger.info(
            f"CLOSED | "
            f"{symbol} | "
            f"SIDE={existing_position.side} | "
            f"PnL={realized_pnl}"
        )

        self.update_unrealized_pnl()

        equity_logger.log_equity()

        snapshot_manager.save_snapshot(
            self
        )

        analytics_engine.process_portfolio(
            self
        )

    # =====================================================
    # PROCESS FILL
    # =====================================================

    def process_fill(
        self,
        fill_event
    ):

        symbol = fill_event.symbol

        fill_side = fill_event.side

        # APPLY FEES
        account_state.apply_fee(
            fill_event.fee
        )

        existing_position = (
            self.open_positions.get(symbol)
        )

        # =====================================================
        # NO POSITION
        # =====================================================

        if existing_position is None:

            # OPEN LONG
            if fill_side == "BUY":

                self.open_position(
                    fill_event,
                    "LONG"
                )

                return

            # OPEN SHORT
            if fill_side == "SELL":

                self.open_position(
                    fill_event,
                    "SHORT"
                )

                return

        # =====================================================
        # LONG -> SHORT FLIP
        # =====================================================

        if (
            existing_position.side == "LONG"
            and fill_side == "SELL"
        ):

            self.close_position(
                existing_position,
                fill_event
            )

            self.open_position(
                fill_event,
                "SHORT"
            )

            return

        # =====================================================
        # SHORT -> LONG FLIP
        # =====================================================

        if (
            existing_position.side == "SHORT"
            and fill_side == "BUY"
        ):

            self.close_position(
                existing_position,
                fill_event
            )

            self.open_position(
                fill_event,
                "LONG"
            )

            return

        # =====================================================
        # DUPLICATE BLOCK
        # =====================================================

        # LONG already open
        if (
            existing_position.side == "LONG"
            and fill_side == "BUY"
        ):

            position_logger.info(
                f"Ignored duplicate LONG "
                f"entry for {symbol}"
            )

            return

        # SHORT already open
        if (
            existing_position.side == "SHORT"
            and fill_side == "SELL"
        ):

            position_logger.info(
                f"Ignored duplicate SHORT "
                f"entry for {symbol}"
            )

            return


portfolio_engine = PortfolioEngine()


def start_portfolio_engine():

    while True:

        fill_event = fill_queue.get()

        portfolio_engine.process_fill(
            fill_event
        )