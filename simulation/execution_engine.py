import uuid
import time

from core.models import OrderEvent

from core.events import (
    signal_queue,
    fill_queue
)

from simulation.exchange_simulator import (
    ExchangeSimulator
)

from simulation.order_validator import (
    OrderValidator
)

from simulation.price_normalizer import (
    normalize_price
)

from simulation.quantity_normalizer import (
    normalize_quantity
)

from risk.position_sizer import (
    PositionSizer
)

from portfolio.account_state import (
    account_state
)

from portfolio.portfolio import (
    portfolio_engine
)

from config.settings import (
    RISK_PER_TRADE
)

from utils.logger import (
    setup_logger
)


order_logger = setup_logger(
    "order_logger",
    "logs/orders/orders.log"
)

rejection_logger = setup_logger(
    "rejection_logger",
    "logs/orders/rejections.log"
)


order_validator = (
    OrderValidator()
)

exchange_simulator = (
    ExchangeSimulator()
)

position_sizer = (
    PositionSizer()
)


class ExecutionEngine:

    def process_signal(
        self,
        signal
    ):

        symbol = signal.symbol

        existing_position = (
            portfolio_engine.open_positions.get(symbol)
        )

        # =====================================================
        # POSITION LOGIC
        # =====================================================

        # LONG SIGNAL
        if signal.signal_type == "LONG":

            # already long -> ignore
            if (
                existing_position
                and existing_position.side == "LONG"
            ):

                return

            # short exists -> close short
            if (
                existing_position
                and existing_position.side == "SHORT"
            ):

                side = "BUY"

            # no position -> open long
            else:

                side = "BUY"

        # SHORT SIGNAL
        else:

            # already short -> ignore
            if (
                existing_position
                and existing_position.side == "SHORT"
            ):

                return

            # long exists -> close long
            if (
                existing_position
                and existing_position.side == "LONG"
            ):

                side = "SELL"

            # no position -> open short
            else:

                side = "SELL"

        execution_price = (
            normalize_price(
                symbol,
                signal.price
            )
        )

        # =====================================================
        # POSITION SIZE
        # =====================================================

        dynamic_size = (
            position_sizer
            .calculate_position_size(

                symbol=symbol,

                portfolio_balance=(
                    account_state.get_equity()
                ),

                entry_price=execution_price,

                risk_percent=RISK_PER_TRADE
            )
        )

        execution_quantity = (
            normalize_quantity(
                symbol,
                dynamic_size
            )
        )

        # =====================================================
        # VALIDATION
        # =====================================================

        is_valid, reason = (
            order_validator.validate_order(
                symbol,
                execution_price,
                execution_quantity
            )
        )

        if not is_valid:

            rejection_logger.warning(
                f"ORDER REJECTED | "
                f"{symbol} | "
                f"{reason}"
            )

            return

        # =====================================================
        # CREATE ORDER
        # =====================================================

        order = OrderEvent(

            order_id=str(uuid.uuid4()),

            symbol=symbol,

            side=side,

            order_type="MARKET",

            quantity=float(
                execution_quantity
            ),

            price=float(
                execution_price
            ),

            timestamp=int(time.time())
        )

        order_logger.info(
            f"Order created | "
            f"{order.symbol} | "
            f"{order.side} | "
            f"QTY={order.quantity} | "
            f"PRICE={order.price}"
        )

        # =====================================================
        # EXECUTE ORDER
        # =====================================================

        fill_event = (
            exchange_simulator.execute_order(
                order
            )
        )

        fill_queue.put(
            fill_event
        )

        print(
            "FILL EVENT SENT TO PORTFOLIO"
        )


portfolio_engine = None


def start_execution_engine():

    global portfolio_engine

    from portfolio.portfolio import (
        portfolio_engine
    )

    engine = ExecutionEngine()

    while True:

        signal = signal_queue.get()

        engine.process_signal(
            signal
        )