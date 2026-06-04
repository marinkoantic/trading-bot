from dataclasses import asdict
from datetime import datetime
import json

from core.eventing.base import BaseEvent


class EventSerializer:

    @staticmethod
    def serialize(event: BaseEvent) -> str:

        data = asdict(event)

        for key, value in data.items():

            if isinstance(value, datetime):
                data[key] = value.isoformat()

            elif hasattr(value, "value"):
                data[key] = value.value

        return json.dumps(data)