import time


class FilterLayer:

    def __init__(self):

        self.last_signal_time = {}

    def cooldown_active(self, symbol, cooldown_seconds=60):

        now = time.time()

        last_time = self.last_signal_time.get(symbol)

        if last_time is None:
            return False

        return (now - last_time) < cooldown_seconds

    def update_signal_time(self, symbol):

        self.last_signal_time[symbol] = time.time()