"""Historical candles: Binance public klines (paginated) and CSV storage.

Only public, unauthenticated market-data endpoints are used.

Binance returns ``close_time = open_time + interval - 1 ms``; internally a
candle covers ``[open_time, open_time + interval)``. The currently forming
candle (``close_time >= now``) is dropped so warmup and backtests only see
closed candles.
"""

from __future__ import annotations

import csv
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.domain import Candle

log = logging.getLogger("data.klines")

MAX_LIMIT = 1000
CSV_FIELDS = ["symbol", "timeframe", "open_time", "close_time", "open", "high", "low", "close", "volume"]


class DataError(RuntimeError):
    pass


@dataclass(frozen=True)
class DataQuality:
    symbol: str
    candles: int
    first_open: int | None
    last_open: int | None
    duplicates: int
    missing: int
    gaps: list[tuple[int, int]]
    invalid: int

    @property
    def ok(self) -> bool:
        return self.duplicates == 0 and self.missing == 0 and self.invalid == 0


def parse_kline(row: list[Any], symbol: str, timeframe: str, timeframe_ms: int) -> Candle:
    open_time = int(row[0])
    return Candle(
        symbol,
        timeframe,
        open_time,
        open_time + timeframe_ms,
        float(row[1]),
        float(row[2]),
        float(row[3]),
        float(row[4]),
        float(row[5]),
        True,
    )


def fetch_klines(
    rest_url: str,
    symbol: str,
    timeframe: str,
    timeframe_ms: int,
    start_ms: int,
    end_ms: int,
    get: Callable[..., Any] | None = None,
    now_ms: int | None = None,
    pause_s: float = 0.2,
    max_retries: int = 5,
) -> list[Candle]:
    """Download closed candles in ``[start_ms, end_ms)`` with pagination and basic rate-limit handling."""
    if get is None:
        import requests

        get = requests.get
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    url = f"{rest_url.rstrip('/')}/api/v3/klines"
    out: list[Candle] = []
    cursor = start_ms - start_ms % timeframe_ms
    retries = 0
    while cursor < end_ms:
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "startTime": cursor,
            "endTime": end_ms - 1,
            "limit": MAX_LIMIT,
        }
        response = get(url, params=params, timeout=10)
        if response.status_code in (418, 429):
            retries += 1
            if retries > max_retries:
                raise DataError(f"rate limited by exchange (HTTP {response.status_code}); giving up")
            wait = float(response.headers.get("Retry-After", 2**retries))
            log.warning("rate limited, sleeping %.1fs", wait)
            time.sleep(wait)
            continue
        if response.status_code != 200:
            raise DataError(f"klines request failed: HTTP {response.status_code}: {response.text[:200]}")
        retries = 0
        rows = response.json()
        if not rows:
            break
        for row in rows:
            candle = parse_kline(row, symbol, timeframe, timeframe_ms)
            if candle.close_time > now_ms or candle.open_time >= end_ms:
                continue  # still forming / outside range
            out.append(candle)
        last_open = int(rows[-1][0])
        if last_open + timeframe_ms <= cursor:
            break
        cursor = last_open + timeframe_ms
        if len(rows) < MAX_LIMIT:
            break
        time.sleep(pause_s)
    return dedupe_sorted(out)


def fetch_recent(
    rest_url: str,
    symbol: str,
    timeframe: str,
    timeframe_ms: int,
    count: int,
    get: Callable[..., Any] | None = None,
    now_ms: int | None = None,
) -> list[Candle]:
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    end = now_ms - now_ms % timeframe_ms  # open time of the forming candle
    return fetch_klines(rest_url, symbol, timeframe, timeframe_ms, end - count * timeframe_ms, end, get, now_ms)


def dedupe_sorted(candles: Iterable[Candle]) -> list[Candle]:
    by_open: dict[int, Candle] = {}
    for c in candles:
        by_open[c.open_time] = c
    return [by_open[k] for k in sorted(by_open)]


def data_quality(symbol: str, candles: list[Candle], timeframe_ms: int) -> DataQuality:
    from candles.aggregator import validate_candle

    seen: set[int] = set()
    dupes = invalid = missing = 0
    gaps: list[tuple[int, int]] = []
    prev: int | None = None
    for c in sorted(candles, key=lambda c: c.open_time):
        if c.open_time in seen:
            dupes += 1
            continue
        seen.add(c.open_time)
        if validate_candle(c) is not None or c.open_time % timeframe_ms:
            invalid += 1
        if prev is not None and c.open_time > prev + timeframe_ms:
            missing += (c.open_time - prev - timeframe_ms) // timeframe_ms
            gaps.append((prev + timeframe_ms, c.open_time))
        prev = c.open_time
    opens = sorted(seen)
    return DataQuality(
        symbol, len(opens), opens[0] if opens else None, opens[-1] if opens else None, dupes, missing, gaps, invalid
    )


def write_csv(path: str | Path, candles: list[Candle]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_FIELDS)
        for c in candles:
            writer.writerow(
                [
                    c.symbol,
                    c.timeframe,
                    c.open_time,
                    c.close_time,
                    repr(c.open),
                    repr(c.high),
                    repr(c.low),
                    repr(c.close),
                    repr(c.volume),
                ]
            )
    tmp.replace(path)  # atomic


def read_csv(path: str | Path, timeframe: str | None = None) -> list[Candle]:
    path = Path(path)
    try:
        with path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            if reader.fieldnames is None or set(CSV_FIELDS) - set(reader.fieldnames):
                raise DataError(f"{path}: expected CSV header {CSV_FIELDS}")
            candles = []
            for line, row in enumerate(reader, start=2):
                try:
                    candles.append(
                        Candle(
                            row["symbol"].upper(),
                            row["timeframe"],
                            int(row["open_time"]),
                            int(row["close_time"]),
                            float(row["open"]),
                            float(row["high"]),
                            float(row["low"]),
                            float(row["close"]),
                            float(row["volume"]),
                            True,
                        )
                    )
                except (TypeError, ValueError) as exc:
                    raise DataError(f"{path}:{line}: {exc}") from exc
    except FileNotFoundError as exc:
        raise DataError(f"data file not found: {path}") from exc
    if timeframe and any(c.timeframe != timeframe for c in candles):
        raise DataError(f"{path}: contains candles that are not {timeframe}")
    return candles
