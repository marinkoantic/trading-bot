import time

from core.eventing.signal import (
    SignalEvent,
)


class CooldownFilter:

    def __init__(
        self,
        cooldown_seconds: int = 10,
    ):

        self.cooldown_seconds = (
            cooldown_seconds
        )

        self.last_signal_time: dict[
            str,
            float
        ] = {}

    def approve(
        self,
        signal: SignalEvent,
    ) -> bool:

        now = time.time()

        last = self.last_signal_time.get(
            signal.symbol,
            0,
        )

        if (
            now - last
            < self.cooldown_seconds
        ):

            return False

        self.last_signal_time[
            signal.symbol
        ] = now

        return True