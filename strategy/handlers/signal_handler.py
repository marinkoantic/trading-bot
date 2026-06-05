from core.eventing.signal import (
    SignalEvent,
)

from risk.risk_manager import (
    RiskManager,
)

from portfolio.portfolio_manager import (
    PortfolioManager,
)

from simulation.execution_simulator import (
    ExecutionSimulator,
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

        self.execution_simulator = (
            ExecutionSimulator()
        )

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

        execution_report = (
            self.execution_simulator
            .execute_market_order(
                symbol=event.symbol,

                side=event.direction.value,

                price=0.000062,

                quantity=1_000_000,
            )
        )

        self.portfolio.open_position(
            execution_report
        )

        print(
            "[EXECUTION] "
            "Simulated execution completed"
        )