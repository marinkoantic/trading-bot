import uuid
import time

from core.models import OrderEvent
from core.events import signal_queue, fill_queue

from simulation.exchange_simulator import ExchangeSimulator

from utils.logger import setup_logger

order_logger = setup_logger(
    "order_logger",
    "logs/orders/orders.log"
)


exchange_simulator = ExchangeSimulator()


class ExecutionEngine:
    def process_signal(self, signal):
        side = "BUY"

        if signal.signal_type == "SHORT":
            side = "SELL"

        order = OrderEvent(
            order_id=str(uuid.uuid4()),

            symbol=signal.symbol,

            side=side,

            order_type="MARKET",

            quantity=0.001,

            price=signal.price,

            timestamp=int(time.time())
        )

        order_logger.info(
            f"Order created: "
            f"{order.symbol} "
            f"{order.side} "
            f"{order.quantity}"
        )

        fill_event = exchange_simulator.execute_order(order)

        fill_queue.put(fill_event)
        
    
def start_execution_engine():
        engine = ExecutionEngine()

        while True:

            signal = signal_queue.get()

            engine.process_signal(signal)