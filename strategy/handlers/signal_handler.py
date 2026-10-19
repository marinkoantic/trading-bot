from core.eventing.enums import (
    SignalDirection,
)

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

        # EXIT FLOW

        if (
            event.direction
            == SignalDirection.EXIT
        ):

            if not (
                self.portfolio.has_position(
                    event.symbol
                )
            ):

                return

            execution_report = (
                self.execution_simulator
                .execute_market_order(
                    symbol=event.symbol,

                    side="EXIT",

                    quantity=1_000_000,
                )
            )

            self.portfolio.close_position(
                execution_report
            )

            print(
                "[EXECUTION] "
                "Exit execution completed"
            )

            return

        # ENTRY FLOW

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