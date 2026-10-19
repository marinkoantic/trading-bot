from decimal import Decimal as D

import pytest

from core.domain import Fill, Side
from portfolio.ledger import Ledger


def fill(fid, side, qty, price, fee="0", ts=1, ref=None):
    return Fill(fid, f"o-{fid}", "BTCUSDT", side, D(qty), D(price), D(fee), ts, D(ref or price))


def test_long_round_trip_regression_no_double_counting():
    """Regression for P0-1: 100 @ 1.0 -> 1.1 must give +10, not +20."""
    lg = Ledger(D("1000"))
    lg.apply_fill(fill("a", Side.BUY, "100", "1.0"))
    assert lg.cash == D("900") and lg.equity() == D("1000")  # P0-2: equity unchanged by opening
    trades = lg.apply_fill(fill("b", Side.SELL, "100", "1.1"))
    assert lg.cash == D("1010") and lg.equity() == D("1010")
    assert lg.realized_pnl == D("10") and lg.positions == {}
    assert trades[0].gross_pnl == D("10") and trades[0].direction == "LONG"
    lg.check_invariants()


def test_fees_booked_once_and_split_onto_trade():
    lg = Ledger(D("1000"))
    lg.apply_fill(fill("a", Side.BUY, "10", "10", fee="0.1"))
    trades = lg.apply_fill(fill("b", Side.SELL, "10", "11", fee="0.11"))
    assert lg.fees_paid == D("0.21")
    assert lg.cash == D("1000") - D("100") - D("0.1") + D("110") - D("0.11")
    assert trades[0].fees == D("0.21") and trades[0].net_pnl == D("9.79")
    lg.check_invariants()


def test_duplicate_fill_is_ignored():
    """Regression for P0-3."""
    lg = Ledger(D("1000"))
    f = fill("a", Side.BUY, "10", "1", fee="0.5")
    assert lg.apply_fill(f) == []
    assert lg.apply_fill(f) is None
    assert lg.fees_paid == D("0.5") and lg.position_qty("BTCUSDT") == D("10")


def test_partial_fills_update_average_entry():
    lg = Ledger(D("1000"))
    lg.apply_fill(fill("a", Side.BUY, "10", "10"))
    lg.apply_fill(fill("b", Side.BUY, "30", "12"))
    pos = lg.positions["BTCUSDT"]
    assert pos.quantity == D("40") and pos.avg_price == D("11.5")
    trades = lg.apply_fill(fill("c", Side.SELL, "20", "13"))
    assert trades[0].gross_pnl == D("30") and trades[0].quantity == D("20")
    assert lg.positions["BTCUSDT"].avg_price == D("11.5")  # avg unchanged when reducing
    lg.check_invariants()


def test_short_accounting():
    lg = Ledger(D("1000"))
    lg.apply_fill(fill("a", Side.SELL, "10", "50"))
    assert lg.cash == D("1500") and lg.equity() == D("1000")
    assert lg.available_funds() == D("500")  # 1x collateral
    lg.mark("BTCUSDT", D("40"))
    assert lg.unrealized_pnl() == D("100")
    trades = lg.apply_fill(fill("b", Side.BUY, "10", "40"))
    assert trades[0].direction == "SHORT" and trades[0].gross_pnl == D("100")
    assert lg.equity() == D("1100")
    lg.check_invariants()


def test_reverse_closes_then_opens_remainder_with_fee_split():
    lg = Ledger(D("1000"))
    lg.apply_fill(fill("a", Side.BUY, "10", "10"))
    trades = lg.apply_fill(fill("b", Side.SELL, "15", "12", fee="0.15"))
    assert trades[0].quantity == D("10") and trades[0].gross_pnl == D("20")
    assert trades[0].fees == D("0.10")
    pos = lg.positions["BTCUSDT"]
    assert pos.quantity == D("-5") and pos.avg_price == D("12") and pos.entry_fees == D("0.05")
    lg.check_invariants()


def test_invariant_holds_over_random_sequence():
    import random

    rng = random.Random(7)
    lg = Ledger(D("10000"))
    for i in range(300):
        side = Side.BUY if rng.random() < 0.5 else Side.SELL
        price = D(str(round(rng.uniform(5, 15), 2)))
        lg.apply_fill(fill(f"f{i}", side, str(rng.randint(1, 20)), str(price), fee="0.01", ts=i))
        lg.mark("BTCUSDT", price)
        lg.check_invariants()


@pytest.mark.parametrize("bad", [dict(qty="0"), dict(price="-1"), dict(fee="-0.1")])
def test_invalid_fill_rejected(bad):
    args = dict(qty="1", price="1", fee="0") | bad
    with pytest.raises(ValueError):
        Ledger(D("1")).apply_fill(fill("x", Side.BUY, args["qty"], args["price"], fee=args["fee"]))
