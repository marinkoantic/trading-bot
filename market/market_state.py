from dataclasses import (
    dataclass,
)


@dataclass(slots=True)
class MarketSnapshot:

    symbol: str

    last_price: float

    bid: float

    ask: float

    spread: float

    timestamp: int


class MarketState:

    _snapshot: (
        MarketSnapshot | None
    ) = None

    @classmethod
    def update(
        cls,
        snapshot: MarketSnapshot,
    ) -> None:

        cls._snapshot = snapshot

    @classmethod
    def get_snapshot(
        cls,
    ) -> (
        MarketSnapshot | None
    ):

        return cls._snapshot