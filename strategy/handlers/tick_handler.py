from core.eventing.market import TickEvent

from strategy.strategy_registry import (
    StrategyRegistry,
)


class TickEventHandler:

    def __init__(
        self,
        registry: StrategyRegistry,
    ):

        self.registry = registry

    def __call__(
        self,
        event: TickEvent,
    ) -> None:

        for strategy in (
            self.registry.strategies
        ):

            strategy.on_tick(event)