from core.eventing.market import TickEvent
from core.eventing.sequence import EventSequence
from core.eventing.signal import (
    SignalEvent,
)


class EventFactory:

    @staticmethod
    def create_tick_event(
        symbol: str,
        price: float,
        volume: float,
        bid: float,
        ask: float,
        source: str = "market_data",
    ) -> TickEvent:

        return TickEvent(
            symbol=symbol,
            price=price,
            volume=volume,
            bid=bid,
            ask=ask,
            source=source,
            sequence_id=EventSequence.next(),
        )
    
    
    @staticmethod
    def create_signal_event(
        symbol: str,
        direction,
        confidence: float,
        strategy_name: str,
        source: str = "strategy",
    ) -> SignalEvent:
        
        return SignalEvent(
            symbol=symbol,
            direction=direction,
            confidence = confidence,
            strategy_name = strategy_name,
            source=source,
            sequence_id=EventSequence.next(),
        )