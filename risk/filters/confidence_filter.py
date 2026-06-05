from core.eventing.signal import (
    SignalEvent,
)


class ConfidenceFilter:

    def __init__(
        self,
        min_confidence: float = 0.7,
    ):

        self.min_confidence = (
            min_confidence
        )

    def approve(
        self,
        signal: SignalEvent,
    ) -> bool:

        return (
            signal.confidence
            >= self.min_confidence
        )