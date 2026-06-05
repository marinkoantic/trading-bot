from abc import ABC, abstractmethod

from core.eventing.market import TickEvent


class BaseStrategy(ABC):

    @abstractmethod
    def on_tick(
        self,
        event: TickEvent,
    ) -> None:
        pass