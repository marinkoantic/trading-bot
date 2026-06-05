from dataclasses import dataclass


@dataclass(slots=True)
class ExecutionReport:

    symbol: str

    side: str

    requested_price: float

    executed_price: float

    quantity: float

    slippage: float

    fee: float