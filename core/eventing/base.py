from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from uuid import uuid4

from core.eventing.enums import EventType


@dataclass(frozen=True, slots=True)
class BaseEvent:

    event_type: EventType = field(init=False)

    event_id: str = field(
        default_factory=lambda: str(uuid4())
    )

    timestamp: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    source: str = "unknown"

    sequence_id: int = 0