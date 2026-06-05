from strategy.base_strategy import (
    BaseStrategy,
)


class DemoStrategy(BaseStrategy):

    def on_tick(self, event):

        print(
            f"[STRATEGY] "
            f"{event.symbol} "
            f"{event.price}"
        )