from dataclasses import dataclass
from typing import Optional


# ============================================
# MARKET DATA EVENTS
# ============================================

@dataclass(slots=True)
class TickEvent:
    symbol: str
    price: float
    quantity: float
    timestamp: int

    trade_id: Optional[int] = None
    is_buyer_maker: Optional[bool] = None


@dataclass(slots=True)
class CandleEvent:
    symbol: str
    timeframe: str

    open: float
    high: float
    low: float
    close: float

    volume: float

    open_time: int
    close_time: int

    is_closed: bool


# ============================================
# STRATEGY EVENTS
# ============================================

@dataclass(slots=True)
class SignalEvent:
    symbol: str

    signal_type: str

    confidence: float

    price: float

    timestamp: int

    strategy_name: str

    reason: str


# ============================================
# EXECUTION EVENTS
# ============================================

@dataclass(slots=True)
class OrderEvent:
    order_id: str

    symbol: str

    side: str
    order_type: str

    quantity: float
    price: float

    timestamp: int


@dataclass(slots=True)
class FillEvent:
    order_id: str
    
    symbol: str
    
    side: str
    
    

    filled_quantity: float
    fill_price: float

    fee: float
    slippage: float

    timestamp: int

    is_partial: bool


# ============================================
# PORTFOLIO EVENTS
# ============================================

@dataclass(slots=True)
class PositionEvent:
    symbol: str
    
    #Long or Short
    side: str

    entry_price: float
    current_price: float

    quantity: float

    unrealized_pnl: float
    realized_pnl: float

    timestamp: int