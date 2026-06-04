import logging

from core.eventing.base import BaseEvent


logger = logging.getLogger("event_bus")


class EventLoggingMiddleware:

    def __call__(self, event: BaseEvent) -> BaseEvent:

        logger.info(
            (
                f"EVENT "
                f"type={event.event_type} "
                f"id={event.event_id} "
                f"seq={event.sequence_id} "
                f"source={event.source}"
            )
        )

        return event