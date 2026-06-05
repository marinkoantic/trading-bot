from core.eventing.signal import (
    SignalEvent,
)

from core.eventing.enums import (
    SignalDirection,
)

from risk.filters.cooldown_filter import (
    CooldownFilter,
)

from risk.filters.confidence_filter import (
    ConfidenceFilter,
)


class RiskManager:

    def __init__(self):

        self.cooldown_filter = (
            CooldownFilter(
                cooldown_seconds=5
            )
        )

        self.confidence_filter = (
            ConfidenceFilter(
                min_confidence=0.7
            )
        )

    def validate_signal(
        self,
        signal: SignalEvent,
    ) -> bool:

        # EXIT signals bypass cooldowns
        # because reducing risk must
        # always be allowed

        if (
            signal.direction
            == SignalDirection.EXIT
        ):

            print(
                "[RISK] EXIT signal "
                "auto-approved"
            )

            return True

        if not (
            self.confidence_filter
            .approve(signal)
        ):

            print(
                "[RISK] Signal rejected "
                "by confidence filter"
            )

            return False

        if not (
            self.cooldown_filter
            .approve(signal)
        ):

            print(
                "[RISK] Signal rejected "
                "by cooldown filter"
            )

            return False

        print(
            "[RISK] Signal approved"
        )

        return True