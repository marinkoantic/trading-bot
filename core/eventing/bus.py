from collections import defaultdict
from typing import DefaultDict

from core.eventing.base import BaseEvent
from core.eventing.enums import EventType
from core.eventing.handlers import EventHandler


class EventBus:

    def __init__(self):

        self._subscribers: DefaultDict[
            EventType,
            list[EventHandler]
        ] = defaultdict(list)

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:

        self._subscribers[event_type].append(handler)

    def publish(self, event: BaseEvent) -> None:

        handlers = self._subscribers.get(
            event.event_type,
            []
        )

        for handler in handlers:
            handler(event)