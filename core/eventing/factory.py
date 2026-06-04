from core.eventing.market import TickEvent
from core.eventing.sequence import EventSequence


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