from dataclasses import dataclass
from datetime import datetime

from core.eventing.base import BaseEvent
from core.eventing.enums import EventType


@dataclass(frozen=True, slots=True)
class TickEvent(BaseEvent):
    symbol: str = ""
    price: float = 0.0
    volume: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    trade_time: datetime | None = None

    def __post_init__(self):
        object.__setattr__(self, "event_type", EventType.MARKET_TICK)


@dataclass(frozen=True, slots=True)
class CandleEvent(BaseEvent):
    symbol: str = ""
    timeframe: str = ""

    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0

    volume: float = 0.0

    candle_open_time: datetime | None = None
    candle_close_time: datetime | None = None

    def __post_init__(self):
        object.__setattr__(self, "event_type", EventType.MARKET_CANDLE)