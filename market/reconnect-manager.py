import time


class ReconnectManager:

    def __init__(self):
        self.reconnect_attempts = 0

    def get_backoff_time(self):

        backoff = min(60, 2 ** self.reconnect_attempts)

        self.reconnect_attempts += 1

        return backoff

    def reset(self):
        self.reconnect_attempts = 0