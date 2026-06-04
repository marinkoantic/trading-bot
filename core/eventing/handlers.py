from typing import Protocol

from core.eventing.base import BaseEvent


class EventHandler(Protocol):

    def __call__(self, event: BaseEvent) -> None:
        """..."""