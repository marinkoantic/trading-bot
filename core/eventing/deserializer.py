import json
from datetime import datetime

from core.eventing.market import TickEvent
from core.eventing.enums import EventType


class EventDeserializer:

    @staticmethod
    def deserialize(line: str):

        data = json.loads(line)

        event_type = data.get("event_type")

        if event_type == EventType.MARKET_TICK.value:

            return TickEvent(
                symbol=data["symbol"],
                price=data["price"],
                volume=data["volume"],
                bid=data["bid"],
                ask=data["ask"],
                source=data["source"],
                sequence_id=data["sequence_id"],
                trade_time=(
                    datetime.fromisoformat(data["trade_time"])
                    if data["trade_time"]
                    else None
                ),
            )

        raise ValueError(
            f"Unknown event type: {event_type}"
        )