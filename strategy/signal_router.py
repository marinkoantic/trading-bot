from core.events import signal_queue

from portfolio.portfolio import (
    portfolio_engine
)

from utils.logger import (
    setup_logger
)


router_logger = setup_logger(
    "router_logger",
    "logs/signals/router.log"
)


class SignalRouter:

    def route_signal(self, signal):

        existing_position = (
            portfolio_engine.open_positions.get(
                signal.symbol
            )
        )

        # ============================================
        # NO POSITION -> ALLOW
        # ============================================

        if existing_position is None:

            signal_queue.put(signal)

            router_logger.info(
                f"{signal.symbol} "
                f"{signal.signal_type} "
                f"forwarded (no position)"
            )

            return

        # ============================================
        # BLOCK DUPLICATE LONG
        # ============================================

        if (
            existing_position.side == "LONG"
            and
            signal.signal_type == "LONG"
        ):

            router_logger.info(
                f"{signal.symbol} "
                f"LONG blocked "
                f"(already LONG)"
            )

            return

        # ============================================
        # BLOCK DUPLICATE SHORT
        # ============================================

        if (
            existing_position.side == "SHORT"
            and
            signal.signal_type == "SHORT"
        ):

            router_logger.info(
                f"{signal.symbol} "
                f"SHORT blocked "
                f"(already SHORT)"
            )

            return

        # ============================================
        # ALLOW REVERSAL
        # ============================================

        signal_queue.put(signal)

        router_logger.info(
            f"{signal.symbol} "
            f"{signal.signal_type} "
            f"forwarded (reversal)"
        )