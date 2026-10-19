from core.eventing.market import (
    TickEvent,
)

from portfolio.portfolio_manager import (
    PortfolioManager,
)


class PortfolioTickHandler:

    def __init__(
        self,
        portfolio: PortfolioManager,
    ):

        self.portfolio = portfolio

    def __call__(
        self,
        event: TickEvent,
    ) -> None:

        self.portfolio.update_price(
            symbol=event.symbol,
            price=event.price,
        )