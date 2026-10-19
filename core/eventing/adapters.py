from core.eventing.factory import EventFactory


def adapt_legacy_tick(raw_tick: dict):

    return EventFactory.create_tick_event(
        symbol=raw_tick.get("symbol", ""),
        price=float(raw_tick.get("price", 0)),
        volume=float(raw_tick.get("volume", 0)),
        bid=float(raw_tick.get("bid", 0)),
        ask=float(raw_tick.get("ask", 0)),
        source="legacy_websocket",
    )