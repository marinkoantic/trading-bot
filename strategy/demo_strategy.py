from core.eventing.enums import (
    SignalDirection,
)

from core.eventing.factory import (
    EventFactory,
)

from core.eventing.runtime_bus import (
    event_bus,
)

from strategy.base_strategy import (
    BaseStrategy,
)


class DemoStrategy(BaseStrategy):

    def __init__(self):

        self.counter = 0

    def on_tick(self, event):

        self.counter += 1

        print(
            f"[STRATEGY] "
            f"{event.symbol} "
            f"{event.price}"
        )

        if self.counter % 20 == 0:

            direction = (
                SignalDirection.EXIT
            )

        else:

            direction = (
                SignalDirection.LONG
            )

        signal = (
            EventFactory.create_signal_event(
                symbol=event.symbol,

                direction=direction,

                confidence=0.8,

                strategy_name=(
                    "DemoStrategy"
                ),
            )
        )

        event_bus.publish(signal)