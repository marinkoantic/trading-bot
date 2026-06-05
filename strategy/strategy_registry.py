from strategy.base_strategy import (
    BaseStrategy,
)


class StrategyRegistry:

    def __init__(self):

        self._strategies: list[
            BaseStrategy
        ] = []

    def register(
        self,
        strategy: BaseStrategy,
    ) -> None:

        self._strategies.append(strategy)

    @property
    def strategies(self):

        return self._strategies