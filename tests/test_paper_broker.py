import random
from decimal import Decimal as D

from core.domain import Order, OrderStatus, OrderType, Side
from portfolio.ledger import Ledger
from simulation.paper_broker import PaperBroker
from tests.helpers import T0, config


def make(*overrides, cash="1000"):
    cfg = config("costs.half_spread_bps=0", "costs.slippage_bps=0", *overrides)
    lg = Ledger(D(cash))
    updates = []
    return cfg, lg, PaperBroker(cfg, lg, random.Random(1), lambda u: updates.append(u.order.status)), updates


def order(oid, side, qty, type_=OrderType.MARKET, stop=None, reduce=False, symbol="BTCUSDT"):
    return Order(oid, symbol, side, type_, D(qty), T0, "test", D(stop) if stop else None, reduce)


def test_market_order_fills_only_on_next_market_data_with_fee():
    _, lg, broker, updates = make()
    o = broker.submit(order("o1", Side.BUY, "1"))
    assert o.status is OrderStatus.ACCEPTED and lg.position_qty("BTCUSDT") == 0
    fills = broker.on_market("BTCUSDT", D("100"), D("101"), D("99"), T0 + 60_000, D("1000"))
    assert len(fills) == 1 and fills[0].price == D("100") and fills[0].fee == D("0.1")
    assert o.status is OrderStatus.FILLED and lg.position_qty("BTCUSDT") == D("1")
    assert updates == [OrderStatus.ACCEPTED, OrderStatus.FILLED]


def test_spread_and_slippage_worsen_price_and_round_against_trader():
    cfg = config("costs.half_spread_bps=1", "costs.slippage_bps=2")
    broker = PaperBroker(cfg, Ledger(D("1000")), random.Random(1))
    broker.submit(order("b", Side.BUY, "1"))
    buy = broker.on_market("BTCUSDT", D("100.005"), D("101"), D("99"), T0)[0]
    assert buy.price == D("100.04")  # 100.005 * 1.0003 = 100.035.. -> ceil to tick 0.01
    assert buy.slippage_cost > 0


def test_seeded_random_slippage_is_reproducible():
    def run():
        cfg = config("costs.random_slippage_bps=10")
        b = PaperBroker(cfg, Ledger(D("100000")), random.Random(cfg.run.seed))
        prices = []
        for i in range(5):
            b.submit(order(f"o{i}", Side.BUY, "0.1"))
            prices.append(b.on_market("BTCUSDT", D("100"), D("100"), D("100"), T0 + i)[0].price)
        return prices

    assert run() == run()


def test_partial_fills_by_volume_participation_then_timeout():
    _, lg, broker, _ = make("execution.max_volume_participation=0.1", "execution.order_timeout_bars=2")
    o = broker.submit(order("o1", Side.BUY, "5"))
    broker.on_market("BTCUSDT", D("10"), D("10"), D("10"), T0, D("20"))  # 2 units available
    assert o.status is OrderStatus.PARTIALLY_FILLED and o.filled_quantity == D("2")
    broker.on_market("BTCUSDT", D("10"), D("10"), D("10"), T0 + 1, D("20"))
    assert o.filled_quantity == D("4") and o.status is OrderStatus.CANCELED
    assert o.reject_reason == "TIMEOUT_UNFILLED_REMAINDER"
    assert lg.position_qty("BTCUSDT") == D("4")
    lg.check_invariants()


def test_insufficient_funds_reduces_or_cancels():
    _, lg, broker, _ = make(cash="100")
    o = broker.submit(order("o1", Side.BUY, "5"))
    broker.on_market("BTCUSDT", D("50"), D("50"), D("50"), T0)
    assert o.filled_quantity == D("1.99800")  # 100 / (50 * 1.001), rounded down to step
    assert lg.cash >= 0
    o2 = broker.submit(order("o2", Side.BUY, "5"))
    broker.on_market("BTCUSDT", D("50"), D("50"), D("50"), T0 + 1)
    assert o2.status is OrderStatus.CANCELED and o2.reject_reason == "INSUFFICIENT_FUNDS"


def test_order_validation_rejections():
    _, _, broker, _ = make()
    assert broker.submit(order("a", Side.BUY, "0")).reject_reason == "INVALID_QUANTITY"
    assert broker.submit(order("b", Side.BUY, "0.000001")).reject_reason == "QUANTITY_NOT_MULTIPLE_OF_STEP"
    assert broker.submit(order("c", Side.BUY, "1", symbol="XRPUSDT")).reject_reason == "UNKNOWN_SYMBOL"
    assert broker.submit(order("d", Side.SELL, "1", reduce=True)).reject_reason == "REDUCE_ONLY_WITHOUT_POSITION"
    assert (
        broker.submit(order("e", Side.SELL, "1", OrderType.STOP_MARKET, stop="90")).reject_reason
        == "STOP_ORDERS_MUST_BE_REDUCE_ONLY"
    )
    assert broker.submit(order("a", Side.BUY, "1")).status is OrderStatus.REJECTED  # idempotent by id


def test_stop_triggers_intrabar_and_handles_gaps():
    _, lg, broker, _ = make()
    broker.submit(order("e", Side.BUY, "2"))
    broker.on_market("BTCUSDT", D("100"), D("100"), D("100"), T0)
    stop = broker.submit(order("s", Side.SELL, "2", OrderType.STOP_MARKET, stop="95", reduce=True))
    assert broker.on_market("BTCUSDT", D("99"), D("101"), D("96"), T0 + 1) == []
    fills = broker.on_market("BTCUSDT", D("97"), D("98"), D("94"), T0 + 2)
    assert fills[0].price == D("95") and stop.status is OrderStatus.FILLED
    broker.submit(order("e2", Side.BUY, "1"))
    broker.on_market("BTCUSDT", D("100"), D("100"), D("100"), T0 + 3)
    broker.submit(order("s2", Side.SELL, "1", OrderType.STOP_MARKET, stop="95", reduce=True))
    gap = broker.on_market("BTCUSDT", D("90"), D("91"), D("89"), T0 + 4)
    assert gap[0].price == D("90")  # gapped through the stop -> filled at the (worse) open
    assert lg.position_qty("BTCUSDT") == 0


def test_reduce_only_never_flips_position():
    _, lg, broker, _ = make()
    broker.submit(order("e", Side.BUY, "1"))
    broker.on_market("BTCUSDT", D("100"), D("100"), D("100"), T0)
    broker.submit(order("x1", Side.SELL, "1", reduce=True))
    x2 = broker.submit(order("x2", Side.SELL, "1", reduce=True))
    broker.on_market("BTCUSDT", D("100"), D("100"), D("100"), T0 + 1)
    assert lg.position_qty("BTCUSDT") == 0
    assert x2.status is OrderStatus.CANCELED and x2.reject_reason == "POSITION_ALREADY_FLAT"
