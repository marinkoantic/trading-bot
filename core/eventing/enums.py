from enum import Enum


class EventType(str, Enum):
    MARKET_TICK = "MARKET_TICK"
    MARKET_CANDLE = "MARKET_CANDLE"

    SIGNAL = "SIGNAL"
    

    ORDER = "ORDER"
    FILL = "FILL"

    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"

    PORTFOLIO_SNAPSHOT = "PORTFOLIO_SNAPSHOT"

    SYSTEM = "SYSTEM"
    
    
class SignalDirection(str, Enum):

    LONG = "LONG"

    SHORT = "SHORT"

    EXIT = "EXIT"