import pytest

from candles.aggregator import CandleAggregator, resample, validate_candle
from tests.helpers import MINUTE, T0, candle, series, shifted


def test_ohlcv_aggregation_and_closing():
    agg = CandleAggregator("BTCUSDT", "1m", MINUTE)
    assert agg.on_trade(100, 1, T0 + 1_000) == []
    assert agg.on_trade(105, 2, T0 + 20_000) == []
    assert agg.on_trade(98, 1, T0 + 59_999) == []
    closed = agg.on_trade(101, 5, T0 + MINUTE)  # first trade of next bar closes the previous one
    assert len(closed) == 1
    c = closed[0]
    assert (c.open, c.high, c.low, c.close, c.volume) == (100, 105, 98, 98, 4)
    assert (c.open_time, c.close_time, c.is_closed) == (T0, T0 + MINUTE, True)


def test_out_of_order_and_invalid_trades_are_rejected():
    agg = CandleAggregator("BTCUSDT", "1m", MINUTE)
    agg.on_trade(100, 1, T0 + MINUTE)
    assert agg.on_trade(90, 1, T0) == []  # older bucket
    assert agg.on_trade(float("nan"), 1, T0 + MINUTE) == []
    assert agg.on_trade(-1, 1, T0 + MINUTE) == []
    assert agg.stats.rejected_out_of_order == 1
    assert agg.stats.rejected_invalid == 2
    closed = agg.on_trade(100, 1, T0 + 2 * MINUTE)
    assert closed[0].low == 100  # rejected trades did not change the candle


def test_gap_is_reported_not_fabricated():
    agg = CandleAggregator("BTCUSDT", "1m", MINUTE)
    agg.on_trade(100, 1, T0)
    closed = agg.on_trade(101, 1, T0 + 4 * MINUTE)
    assert len(closed) == 1  # no synthetic candles for minutes 1..3
    assert agg.stats.missing_intervals == 3
    assert agg.stats.gaps == [(T0 + MINUTE, T0 + 4 * MINUTE)]


def test_seed_last_closed_prevents_overlap_with_warmup():
    agg = CandleAggregator("BTCUSDT", "1m", MINUTE)
    agg.seed_last_closed(T0)
    assert agg.on_trade(100, 1, T0 + 5) == []
    assert agg.stats.rejected_out_of_order == 1


def test_flush_closes_after_boundary_only():
    agg = CandleAggregator("BTCUSDT", "1m", MINUTE)
    agg.on_trade(100, 1, T0)
    assert agg.flush(T0 + MINUTE - 1) == []
    assert len(agg.flush(T0 + MINUTE)) == 1


def test_resample_only_complete_buckets():
    candles = series([float(x) for x in range(1, 13)])  # 12 one-minute candles from T0
    five = resample(candles, "5m", 5 * MINUTE)
    offset = (T0 % (5 * MINUTE)) // MINUTE
    assert all(c.close_time - c.open_time == 5 * MINUTE for c in five)
    expected_full = (12 - ((5 - offset) % 5)) // 5
    assert len(five) == expected_full
    first = five[0]
    members = [c for c in candles if first.open_time <= c.open_time < first.close_time]
    assert first.open == members[0].open and first.close == members[-1].close
    assert first.high == max(c.high for c in members)
    with pytest.raises(ValueError):
        resample(candles, "90s", 90_000)


def test_validate_candle():
    good = candle(0, 10, open_=9, high=11, low=8)
    assert validate_candle(good) is None
    assert validate_candle(shifted(good, high=8.5)) == "inconsistent OHLC"
    assert validate_candle(shifted(good, close=float("inf"))) == "non-finite value"
    assert validate_candle(shifted(good, is_closed=False)) == "candle not closed"
    assert validate_candle(shifted(good, low=0)) == "non-positive price"
