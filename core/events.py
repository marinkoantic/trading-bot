from queue import Queue


# ============================================
# CENTRAL EVENT QUEUES
# ============================================

tick_queue = Queue(maxsize=10000)

candle_queue = Queue(maxsize=5000)

signal_queue = Queue(maxsize=2000)

order_queue = Queue(maxsize=2000)

fill_queue = Queue(maxsize=2000)

position_queue = Queue(maxsize=2000)

analytics_queue = Queue(maxsize=5000)