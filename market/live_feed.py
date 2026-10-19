"""Public Binance aggTrade WebSocket feed (market data only - no account access).

* One combined stream for all configured symbols
  (``/stream?streams=btcusdt@aggTrade/ethusdt@aggTrade``).
* Reconnect with exponential backoff and full jitter, capped at
  ``market.reconnect_max_backoff_seconds``; the attempt counter resets after a
  connection delivered data.
* Ping/pong keepalive via websocket-client; stale-data detection via
  :meth:`LiveFeed.seconds_since_last_message`.
* Sequence gaps are detected from the aggregate trade id ``a`` per symbol.
* :meth:`stop` closes the socket and ends :meth:`run` promptly.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

log = logging.getLogger("market.feed")


@dataclass(frozen=True, slots=True)
class TradeTick:
    symbol: str
    price: Decimal
    quantity: Decimal
    ts: int
    agg_id: int
    after_gap: bool = False  # at least one trade was missed right before this one


def parse_agg_trade(raw: str) -> TradeTick | None:
    """Parse a (combined-stream) aggTrade message. Returns None for non-trade messages."""
    data = json.loads(raw)
    if "data" in data:
        data = data["data"]
    if data.get("e") != "aggTrade":
        return None
    price, qty = Decimal(data["p"]), Decimal(data["q"])
    if not (price.is_finite() and qty.is_finite()) or price <= 0 or qty < 0:
        raise ValueError(f"invalid trade values p={data['p']} q={data['q']}")
    return TradeTick(data["s"].upper(), price, qty, int(data["T"]), int(data["a"]))


def backoff_delay(attempt: int, cap: float, rng: random.Random, base: float = 1.0) -> float:
    """Full-jitter exponential backoff: uniform(0, min(cap, base * 2**attempt))."""
    return rng.uniform(0, min(cap, base * 2**attempt))


@dataclass
class FeedStatus:
    connected: bool = False
    connects: int = 0
    reconnects: int = 0
    messages: int = 0
    parse_errors: int = 0
    sequence_gaps: int = 0
    last_message_monotonic: float | None = None
    last_agg_id: dict[str, int] = field(default_factory=dict)


class LiveFeed:
    def __init__(
        self,
        ws_url: str,
        symbols: tuple[str, ...],
        on_trade: Callable[[TradeTick], None],
        max_backoff: float = 60,
        rng: random.Random | None = None,
        ws_factory: Callable | None = None,
    ):
        streams = "/".join(f"{s.lower()}@aggTrade" for s in symbols)
        self.url = f"{ws_url.rstrip('/')}/stream?streams={streams}"
        self.symbols = symbols
        self.on_trade = on_trade
        self.max_backoff = max_backoff
        self.rng = rng or random.Random()
        self.status = FeedStatus()
        self._stop = threading.Event()
        self._ws = None
        self._lock = threading.Lock()
        self._ws_factory = ws_factory

    def seconds_since_last_message(self) -> float | None:
        last = self.status.last_message_monotonic
        return None if last is None else time.monotonic() - last

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._ws is not None:
                try:
                    self._ws.close()
                except Exception:  # noqa: BLE001 - closing a dead socket must never raise during shutdown
                    log.debug("error while closing websocket", exc_info=True)

    def handle_message(self, raw: str) -> None:
        try:
            tick = parse_agg_trade(raw)
        except (ValueError, KeyError, TypeError) as exc:
            self.status.parse_errors += 1
            log.warning("unparseable message: %s", exc)
            return
        self.status.messages += 1
        self.status.last_message_monotonic = time.monotonic()
        if tick is None or tick.symbol not in self.symbols:
            return
        last = self.status.last_agg_id.get(tick.symbol)
        if last is not None and tick.agg_id <= last:
            return  # duplicate / replayed message
        if last is not None and tick.agg_id > last + 1:
            tick = replace(tick, after_gap=True)
            self.status.sequence_gaps += 1
            log.warning("sequence gap %s: %d -> %d", tick.symbol, last, tick.agg_id, extra={"symbol": tick.symbol})
        self.status.last_agg_id[tick.symbol] = tick.agg_id
        self.on_trade(tick)

    def run(self) -> None:
        if self._ws_factory is None:
            import websocket

            def factory(**kw):
                return websocket.WebSocketApp(self.url, **kw)
        else:
            factory = self._ws_factory
        attempt = 0
        while not self._stop.is_set():
            got_data = threading.Event()

            def on_open(_ws):
                self.status.connected = True
                self.status.connects += 1
                log.info("websocket connected: %s", self.url)

            def on_message(_ws, raw, got_data=got_data):
                got_data.set()
                self.handle_message(raw)

            def on_error(_ws, error):
                log.warning("websocket error: %s", error)

            def on_close(_ws, code, msg):
                self.status.connected = False
                level = logging.INFO if self._stop.is_set() else logging.WARNING  # expected on shutdown
                log.log(level, "websocket closed (%s %s)", code, msg)

            ws = factory(on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
            with self._lock:
                self._ws = ws
            try:
                ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:  # noqa: BLE001 - any transport failure leads to a controlled reconnect
                log.exception("websocket loop crashed")
            self.status.connected = False
            if self._stop.is_set():
                break
            attempt = 0 if got_data.is_set() else attempt + 1
            delay = backoff_delay(attempt, self.max_backoff, self.rng)
            self.status.reconnects += 1
            log.warning("reconnecting in %.1fs (attempt %d)", delay, attempt)
            self._stop.wait(delay)
