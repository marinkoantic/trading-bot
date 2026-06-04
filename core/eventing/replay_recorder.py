from pathlib import Path

from core.eventing.base import BaseEvent
from core.eventing.serializer import EventSerializer


class ReplayRecorderMiddleware:

    def __init__(
        self,
        path: str = "storage/events/events.jsonl",
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    def __call__(
        self,
        event: BaseEvent,
    ) -> BaseEvent:

        serialized = EventSerializer.serialize(event)

        with open(self.path, "a") as file:
            file.write(serialized + "\n")

        return event