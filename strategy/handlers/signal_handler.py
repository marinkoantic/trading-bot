from core.eventing.signal import (
    SignalEvent,
)

from risk.risk_manager import (
    RiskManager,
)


class SignalEventHandler:

    def __init__(self):

        self.risk_manager = (
            RiskManager()
        )

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

        approved = (
            self.risk_manager
            .validate_signal(event)
        )

        if not approved:
            return

        print(
            "[EXECUTION] "
            "Signal passed risk checks"
        )