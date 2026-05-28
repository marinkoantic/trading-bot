from collections import deque


class TickBuffer:

    def __init__(self, max_size=10000):
        self.buffer = deque(maxlen=max_size)

    def add_tick(self, tick):
        self.buffer.append(tick)

    def get_ticks(self):
        return list(self.buffer)

    def clear(self):
        self.buffer.clear()