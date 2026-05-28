from core.events import signal_queue


class SignalRouter:

    def route_signal(self, signal):

        signal_queue.put(signal)