from core.eventing.signal import (
    SignalEvent,
)


class SignalEventHandler:

    def __call__(
        self,
        event: SignalEvent,
    ) -> None:

        print(
            f"[SIGNAL] "
            f"{event.strategy_name} "
            f"{event.direction} "
            f"confidence={event.confidence}"
        )