from decimal import Decimal

import pytest

from core.config import PAPER_ONLY, ConfigError, TradingMode, load_config


def test_default_config_is_paper_and_valid():
    cfg = load_config(environ={})
    assert PAPER_ONLY is True
    assert cfg.run.mode is TradingMode.PAPER
    assert cfg.risk.enable_shorts is False
    assert "LUNCUSDT" in cfg.symbols
    assert len(cfg.config_hash()) == 16


@pytest.mark.parametrize("mode", ["live", "LIVE", "production", "real", ""])
def test_live_or_unknown_mode_fails_closed(mode):
    with pytest.raises(ConfigError, match="PAPER_ONLY"):
        load_config(overrides=[f"run.mode={mode}"], environ={})


def test_live_mode_via_env_fails_closed():
    with pytest.raises(ConfigError, match="PAPER_ONLY"):
        load_config(environ={"TB_RUN__MODE": "live"})


def test_credentials_are_rejected():
    with pytest.raises(ConfigError, match="credential"):
        load_config(overrides=["market.api_key=abc"], environ={})


def test_unknown_key_and_section_rejected():
    with pytest.raises(ConfigError, match="Unknown key"):
        load_config(overrides=["risk.max_open_positon=2"], environ={})
    with pytest.raises(ConfigError, match="Unknown config section"):
        load_config(overrides=["exchange.foo=1"], environ={})


def test_type_errors_are_reported():
    with pytest.raises(ConfigError, match="integer"):
        load_config(overrides=["risk.max_open_positions=two"], environ={})
    with pytest.raises(ConfigError, match="true/false"):
        load_config(overrides=["risk.enable_shorts=1"], environ={})


@pytest.mark.parametrize(
    "override",
    [
        "risk.risk_per_trade_pct=0",
        "risk.risk_per_trade_pct=50",
        "risk.max_position_notional_pct=80",  # > max_total_exposure_pct (50)
        "account.start_cash=-1",
        "costs.taker_fee_rate=0.5",
        "strategy.fast_period=60",
        "run.timeframe=7m",
        "run.symbols=['DOGEUSDT']",  # no exchange rules configured
        "risk.allow_reversal=true",  # needs enable_shorts
        "market.ws_url='ws://insecure'",
    ],
)
def test_invalid_values_fail(override):
    with pytest.raises(ConfigError):
        load_config(overrides=[override], environ={})


def test_overrides_and_env_precedence():
    cfg = load_config(
        overrides=["risk.max_open_positions=1", "run.symbols=['BTCUSDT','ETHUSDT']"],
        environ={"TB_RISK__MAX_OPEN_POSITIONS": "2", "TB_COSTS__SLIPPAGE_BPS": "5"},
    )
    assert cfg.risk.max_open_positions == 1  # CLI beats env
    assert cfg.costs.slippage_bps == Decimal("5")
    assert cfg.run.symbols == ("BTCUSDT", "ETHUSDT")


def test_profiles_switch_mode_but_never_to_live():
    assert load_config("backtest", environ={}).run.mode is TradingMode.BACKTEST
    assert load_config("dev", environ={}).run.mode is TradingMode.PAPER
    with pytest.raises(ConfigError):
        load_config("does_not_exist", environ={})


def test_config_hash_changes_with_parameters():
    a = load_config(environ={}).config_hash()
    b = load_config(overrides=["strategy.fast_period=10"], environ={}).config_hash()
    assert a != b
