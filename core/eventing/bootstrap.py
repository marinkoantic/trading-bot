from core.eventing.logging_middleware import (
    EventLoggingMiddleware,
)
from core.eventing.replay_recorder import (
    ReplayRecorderMiddleware,
)
from core.eventing.runtime_bus import (
    event_bus,
)


def setup_eventing() -> None:

    event_bus.add_middleware(
        EventLoggingMiddleware()
    )

    event_bus.add_middleware(
        ReplayRecorderMiddleware()
    )