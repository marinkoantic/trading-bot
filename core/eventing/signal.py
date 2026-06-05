from dataclasses import dataclass, field

from core.eventing.base import BaseEvent
from core.eventing.enums import (
    EventType,
    SignalDirection,
)


@dataclass(frozen=True, slots=True)
class SignalEvent(BaseEvent):

    symbol: str = ""

    direction: SignalDirection = (
        SignalDirection.LONG
    )

    confidence: float = 0.0

    strategy_name: str = ""

    def __post_init__(self):

        object.__setattr__(
            self,
            "event_type",
            EventType.SIGNAL
        )