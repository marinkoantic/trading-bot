from core.eventing.signal import (
    SignalEvent,
)

from risk.risk_manager import (
    RiskManager,
)

from portfolio.portfolio_manager import (
    PortfolioManager,
)


class SignalEventHandler:

    def __init__(
        self,
        portfolio: PortfolioManager,
    ):

        self.risk_manager = (
            RiskManager()
        )

        self.portfolio = portfolio

    def __call__(
        self,
        event: SignalEvent,
    ) -> None:

        print(
            f"[SIGNAL] "
            f"{event.strategy_name} "
            f"{event.direction} "
            f"confidence={event.confidence}"
        )

        approved = (
            self.risk_manager
            .validate_signal(event)
        )

        if not approved:
            return

        if self.portfolio.has_position(
            event.symbol
        ):

            print(
                "[PORTFOLIO] "
                "Position already exists"
            )

            return

        self.portfolio.open_position(
            symbol=event.symbol,

            quantity=1_000_000,

            entry_price=0.000062,

            side=event.direction.value,
        )

        print(
            "[EXECUTION] "
            "Mock execution completed"
        )