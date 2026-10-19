import math

import pytest

from indicators.atr import ATR
from indicators.ema import EMA, calculate_ema
from indicators.rsi import RSI, calculate_rsi

# Wilder RSI reference example (StockCharts "RSI" ChartSchool spreadsheet, 14 periods)
WILDER_CLOSES = [
    44.3389,
    44.0902,
    44.1497,
    43.6124,
    44.3278,
    44.8264,
    45.0955,
    45.4245,
    45.8433,
    46.0826,
    45.8931,
    46.0328,
    45.6140,
    46.2820,
    46.2820,
    46.0028,
    46.0328,
    46.4116,
    46.2222,
    45.6439,
]
WILDER_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97]


def test_ema_warmup_and_seed():
    ema = EMA(3)
    assert ema.update(1) is None
    assert ema.update(2) is None
    assert ema.update(3) == pytest.approx(2.0)  # SMA seed
    assert ema.update(4) == pytest.approx(3.0)  # 2 + 0.5 * (4 - 2)
    assert ema.update(4) == pytest.approx(3.5)


def test_ema_batch_matches_incremental_and_constant_series():
    prices = [float(i % 7) for i in range(50)]
    ema = EMA(10)
    for p in prices:
        last = ema.update(p)
    assert calculate_ema(prices, 10) == pytest.approx(last)
    assert calculate_ema([5.0] * 30, 10) == pytest.approx(5.0)
    assert calculate_ema([1.0, 2.0], 10) is None


def test_rsi_matches_wilder_reference():
    rsi = RSI(14)
    values = [rsi.update(p) for p in WILDER_CLOSES]
    assert all(v is None for v in values[:14])
    assert [round(v, 2) for v in values[14:]] == pytest.approx(WILDER_RSI, abs=0.01)


def test_rsi_edge_cases():
    assert calculate_rsi([1.0] * 20, 14) == 50.0  # flat -> neutral
    assert calculate_rsi([float(i) for i in range(20)], 14) == 100.0
    assert calculate_rsi([float(20 - i) for i in range(20)], 14) == pytest.approx(0.0)
    assert calculate_rsi([1.0] * 14, 14) is None  # needs period + 1 prices


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_indicators_reject_non_finite(bad):
    with pytest.raises(ValueError):
        EMA(3).update(bad)
    with pytest.raises(ValueError):
        RSI(3).update(bad)
    with pytest.raises(ValueError):
        ATR(3).update(bad, 1, 1)


def test_atr_true_range_and_wilder_smoothing():
    atr = ATR(2)
    assert atr.update(10, 8, 9) is None  # primes previous close
    assert atr.update(11, 9, 10) is None  # TR = 2
    assert atr.update(14, 10, 13) == pytest.approx(3.0)  # TR = 4 -> seed (2+4)/2
    assert atr.update(13, 12, 12.5) == pytest.approx(2.0)  # TR = 1 -> (3*1 + 1)/2
    assert ATR(2).update(1, 1, 1) is None
    with pytest.raises(ValueError):
        ATR(2).update(1, 2, 1)
