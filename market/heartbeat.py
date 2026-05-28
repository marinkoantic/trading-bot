import time


class Heartbeat:

    def __init__(self):

        self.last_update = time.time()

    def update(self):

        self.last_update = time.time()

    def is_stale(self, stale_seconds=30):

        return (
            time.time() - self.last_update
        ) > stale_seconds


heartbeat = Heartbeat()