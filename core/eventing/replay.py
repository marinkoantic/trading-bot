from pathlib import Path

from core.eventing.bus import EventBus
from core.eventing.deserializer import (
    EventDeserializer,
)


class ReplayEngine:

    def __init__(
        self,
        bus: EventBus,
        path: str,
    ):

        self.bus = bus
        self.path = Path(path)

    def replay(self) -> None:

        with open(self.path, "r") as file:

            for line in file:

                line = line.strip()

                if not line:
                    continue

                event = EventDeserializer.deserialize(
                    line
                )

                self.bus.publish(event)