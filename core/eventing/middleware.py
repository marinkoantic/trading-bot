from typing import Protocol

from core.eventing.base import BaseEvent


class EventMiddleware(Protocol):

    def __call__(self, event: BaseEvent) -> BaseEvent:
        """..."""