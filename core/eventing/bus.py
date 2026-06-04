from collections import defaultdict
from typing import DefaultDict

from core.eventing.base import BaseEvent
from core.eventing.enums import EventType
from core.eventing.handlers import EventHandler
from core.eventing.middleware import EventMiddleware


class EventBus:

    def __init__(self):

        self._subscribers: DefaultDict[
            EventType,
            list[EventHandler]
        ] = defaultdict(list)

        self._middleware: list[EventMiddleware] = []

    def subscribe(
        self,
        event_type: EventType,
        handler: EventHandler,
    ) -> None:

        self._subscribers[event_type].append(handler)

    def add_middleware(
        self,
        middleware: EventMiddleware,
    ) -> None:

        self._middleware.append(middleware)

    def publish(self, event: BaseEvent) -> None:

        for middleware in self._middleware:
            event = middleware(event)

        handlers = self._subscribers.get(
            event.event_type,
            []
        )

        for handler in handlers:
            handler(event)