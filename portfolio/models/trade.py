from dataclasses import dataclass


@dataclass(slots=True)
class Trade:

    symbol: str

    side: str

    quantity: float

    entry_price: float

    exit_price: float

    realized_pnl: float

    fee: float