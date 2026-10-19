"""Central, validated configuration (fail closed).

Sources, in increasing precedence:
  1. ``config/default.toml``
  2. ``config/profiles/<profile>.toml`` (optional)
  3. environment variables ``TB_<SECTION>__<KEY>`` (e.g. ``TB_RISK__MAX_OPEN_POSITIONS=2``)
  4. explicit overrides ``section.key=value`` (CLI ``--set``)

Safety rules:
  * The only supported modes are ``paper`` and ``backtest``. Anything else -
    including ``live`` - raises :class:`ConfigError`. There is no code path that
    submits orders to a real exchange.
  * Unknown sections/keys are rejected so a typo can never silently fall back
    to a default.
  * Secrets are never needed (only public market data is used) and keys that
    look like credentials are rejected.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tomllib
from dataclasses import asdict, dataclass, field, fields
from decimal import Decimal, InvalidOperation
from enum import Enum, StrEnum
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "default.toml"
PROFILE_DIR = PROJECT_ROOT / "config" / "profiles"

TIMEFRAME_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

PAPER_ONLY = True  # hard safety boundary; not configurable

_SECRET_MARKERS = ("api_key", "apikey", "secret", "password", "token", "passphrase")


class ConfigError(ValueError):
    """Raised for any invalid or unsafe configuration."""


class TradingMode(StrEnum):
    PAPER = "paper"
    BACKTEST = "backtest"


@dataclass(frozen=True)
class RunConfig:
    mode: TradingMode = TradingMode.PAPER
    symbols: tuple[str, ...] = ("LUNCUSDT",)
    timeframe: str = "1m"
    database: str = "storage/sqlite/trading.db"
    log_dir: str = "logs"
    report_dir: str = "storage/reports"
    seed: int = 42
    equity_snapshot_every_bars: int = 1


@dataclass(frozen=True)
class AccountConfig:
    start_cash: Decimal = Decimal("1000")
    quote_asset: str = "USDT"


@dataclass(frozen=True)
class CostConfig:
    taker_fee_rate: Decimal = Decimal("0.001")
    maker_fee_rate: Decimal = Decimal("0.001")
    half_spread_bps: Decimal = Decimal("1")
    slippage_bps: Decimal = Decimal("2")
    random_slippage_bps: Decimal = Decimal("0")


@dataclass(frozen=True)
class ExecutionConfig:
    max_volume_participation: Decimal = Decimal("0.1")
    order_timeout_bars: int = 3


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade_pct: Decimal = Decimal("1")
    max_position_notional_pct: Decimal = Decimal("25")
    max_total_exposure_pct: Decimal = Decimal("50")
    max_open_positions: int = 3
    max_daily_loss_pct: Decimal = Decimal("3")
    max_drawdown_pct: Decimal = Decimal("20")
    enable_shorts: bool = False
    allow_reversal: bool = False


@dataclass(frozen=True)
class StrategyConfig:
    name: str = "ema_rsi"
    signal_mode: str = "crossover"
    fast_period: int = 20
    slow_period: int = 50
    rsi_period: int = 14
    rsi_long_min: float = 55.0
    rsi_short_max: float = 45.0
    atr_period: int = 14
    atr_stop_multiple: float = 2.0
    cooldown_bars: int = 3

    @property
    def warmup_bars(self) -> int:
        return max(self.slow_period + 1, self.rsi_period + 2, self.atr_period + 1)


@dataclass(frozen=True)
class SymbolRules:
    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    min_notional: Decimal
    max_qty: Decimal = Decimal("90000000000")


@dataclass(frozen=True)
class MarketConfig:
    ws_url: str = "wss://stream.binance.com:9443"
    rest_url: str = "https://api.binance.com"
    stale_after_seconds: int = 30
    warmup_candles: int = 200
    reconnect_max_backoff_seconds: int = 60
    queue_size: int = 10_000


@dataclass(frozen=True)
class AppConfig:
    run: RunConfig = field(default_factory=RunConfig)
    account: AccountConfig = field(default_factory=AccountConfig)
    costs: CostConfig = field(default_factory=CostConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    market: MarketConfig = field(default_factory=MarketConfig)
    symbols: dict[str, SymbolRules] = field(default_factory=dict)
    profile: str = "default"

    @property
    def timeframe_ms(self) -> int:
        return TIMEFRAME_MS[self.run.timeframe]

    def rules_for(self, symbol: str) -> SymbolRules:
        try:
            return self.symbols[symbol]
        except KeyError as exc:  # validated at load time; defensive
            raise ConfigError(f"No exchange rules configured for {symbol}") from exc

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))

    def config_hash(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


_SECTIONS: dict[str, type] = {
    "run": RunConfig,
    "account": AccountConfig,
    "costs": CostConfig,
    "execution": ExecutionConfig,
    "risk": RiskConfig,
    "strategy": StrategyConfig,
    "market": MarketConfig,
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    return value


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc


def _parse_scalar(raw: str) -> Any:
    """Parse an env/CLI override value using TOML scalar syntax, else keep as string."""
    try:
        return tomllib.loads(f"v = {raw}")["v"]
    except tomllib.TOMLDecodeError:
        return raw


def _apply_override(data: dict[str, Any], dotted: str, raw: str) -> None:
    parts = dotted.strip().split(".")
    if len(parts) != 2 or not all(parts):
        raise ConfigError(f"Override must look like section.key=value, got {dotted!r}")
    section, key = (p.lower() for p in parts)
    data.setdefault(section, {})[key] = _parse_scalar(raw)


def _check_no_secrets(data: dict[str, Any], prefix: str = "") -> None:
    for key, value in data.items():
        name = f"{prefix}{key}"
        if any(marker in key.lower() for marker in _SECRET_MARKERS):
            raise ConfigError(
                f"Config key {name!r} looks like a credential. This system is PAPER_ONLY "
                "and needs no exchange credentials; remove it."
            )
        if isinstance(value, dict):
            _check_no_secrets(value, f"{name}.")


def _coerce(section: str, name: str, target: Any, value: Any) -> Any:
    where = f"{section}.{name}"
    if target is Decimal:
        if isinstance(value, bool):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        try:
            result = Decimal(str(value))
        except InvalidOperation as exc:
            raise ConfigError(f"{where}: expected a number, got {value!r}") from exc
        if not result.is_finite():
            raise ConfigError(f"{where}: must be finite")
        return result
    if target is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where}: expected true/false, got {value!r}")
        return value
    if target is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where}: expected an integer, got {value!r}")
        return value
    if target is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ConfigError(f"{where}: expected a number, got {value!r}")
        if not math.isfinite(value):
            raise ConfigError(f"{where}: must be finite")
        return float(value)
    if target is str:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: expected a string, got {value!r}")
        return value
    if target is TradingMode:
        if not isinstance(value, str):
            raise ConfigError(f"{where}: expected a string, got {value!r}")
        try:
            return TradingMode(value.lower())
        except ValueError as exc:
            raise ConfigError(
                f"{where}={value!r} is not allowed. This system is PAPER_ONLY; "
                f"allowed modes: {[m.value for m in TradingMode]}. Live trading is not "
                "implemented and cannot be enabled."
            ) from exc
    if target == tuple[str, ...]:
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"{where}: expected a list of strings, got {value!r}")
        return tuple(v.upper() for v in value)
    raise ConfigError(f"{where}: unsupported type {target}")  # pragma: no cover


_TYPE_NAMES = {
    "Decimal": Decimal,
    "bool": bool,
    "int": int,
    "float": float,
    "str": str,
    "TradingMode": TradingMode,
    "tuple[str, ...]": tuple[str, ...],
}


def _build_section(name: str, cls: type, values: dict[str, Any]) -> Any:
    known = {f.name: f for f in fields(cls)}
    unknown = set(values) - set(known)
    if unknown:
        raise ConfigError(f"Unknown key(s) in [{name}]: {sorted(unknown)}")
    kwargs = {}
    for key, value in values.items():
        target = _TYPE_NAMES[known[key].type] if isinstance(known[key].type, str) else known[key].type
        kwargs[key] = _coerce(name, key, target, value)
    return cls(**kwargs)


def _build_symbols(raw: dict[str, Any]) -> dict[str, SymbolRules]:
    result: dict[str, SymbolRules] = {}
    for symbol, values in raw.items():
        if not isinstance(values, dict):
            raise ConfigError(f"[symbols.{symbol}] must be a table")
        result[symbol.upper()] = _build_section(f"symbols.{symbol}", SymbolRules, values)
    return result


def _validate(cfg: AppConfig) -> None:
    errors: list[str] = []

    def require(cond: bool, message: str) -> None:
        if not cond:
            errors.append(message)

    run, risk, costs, strat, ex = cfg.run, cfg.risk, cfg.costs, cfg.strategy, cfg.execution
    require(bool(run.symbols), "run.symbols must not be empty")
    require(len(set(run.symbols)) == len(run.symbols), "run.symbols contains duplicates")
    require(run.timeframe in TIMEFRAME_MS, f"run.timeframe must be one of {list(TIMEFRAME_MS)}")
    require(run.equity_snapshot_every_bars >= 1, "run.equity_snapshot_every_bars must be >= 1")
    for symbol in run.symbols:
        require(symbol.isalnum(), f"run.symbols: invalid symbol {symbol!r}")
        require(symbol in cfg.symbols, f"missing [symbols.{symbol}] exchange rules")
    for symbol, rules in cfg.symbols.items():
        for attr in ("tick_size", "step_size", "min_qty", "min_notional", "max_qty"):
            require(getattr(rules, attr) > 0, f"symbols.{symbol}.{attr} must be > 0")
        require(rules.max_qty >= rules.min_qty, f"symbols.{symbol}.max_qty must be >= min_qty")

    require(cfg.account.start_cash > 0, "account.start_cash must be > 0")
    for attr in ("taker_fee_rate", "maker_fee_rate"):
        require(Decimal("0") <= getattr(costs, attr) < Decimal("0.05"), f"costs.{attr} must be in [0, 0.05)")
    for attr in ("half_spread_bps", "slippage_bps", "random_slippage_bps"):
        require(Decimal("0") <= getattr(costs, attr) <= Decimal("500"), f"costs.{attr} must be in [0, 500]")

    require(Decimal("0") < ex.max_volume_participation <= 1, "execution.max_volume_participation must be in (0, 1]")
    require(ex.order_timeout_bars >= 1, "execution.order_timeout_bars must be >= 1")

    require(Decimal("0") < risk.risk_per_trade_pct <= 5, "risk.risk_per_trade_pct must be in (0, 5]")
    require(Decimal("0") < risk.max_position_notional_pct <= 100, "risk.max_position_notional_pct must be in (0, 100]")
    require(Decimal("0") < risk.max_total_exposure_pct <= 100, "risk.max_total_exposure_pct must be in (0, 100]")
    require(
        risk.max_position_notional_pct <= risk.max_total_exposure_pct,
        "risk.max_position_notional_pct must be <= risk.max_total_exposure_pct",
    )
    require(risk.max_open_positions >= 1, "risk.max_open_positions must be >= 1")
    require(Decimal("0") < risk.max_daily_loss_pct <= 100, "risk.max_daily_loss_pct must be in (0, 100]")
    require(Decimal("0") < risk.max_drawdown_pct <= 100, "risk.max_drawdown_pct must be in (0, 100]")
    require(not risk.allow_reversal or risk.enable_shorts, "risk.allow_reversal requires risk.enable_shorts")

    require(strat.name == "ema_rsi", "strategy.name: only 'ema_rsi' is implemented")
    require(strat.signal_mode in ("crossover", "state"), "strategy.signal_mode must be 'crossover' or 'state'")
    require(1 < strat.fast_period < strat.slow_period, "strategy: need 1 < fast_period < slow_period")
    require(strat.rsi_period >= 2, "strategy.rsi_period must be >= 2")
    require(
        0 <= strat.rsi_short_max <= strat.rsi_long_min <= 100,
        "strategy: need 0 <= rsi_short_max <= rsi_long_min <= 100",
    )
    require(strat.atr_period >= 2, "strategy.atr_period must be >= 2")
    require(strat.atr_stop_multiple > 0, "strategy.atr_stop_multiple must be > 0")
    require(strat.cooldown_bars >= 0, "strategy.cooldown_bars must be >= 0")

    mkt = cfg.market
    require(mkt.ws_url.startswith("wss://"), "market.ws_url must use wss://")
    require(mkt.rest_url.startswith("https://"), "market.rest_url must use https://")
    require(mkt.stale_after_seconds >= 5, "market.stale_after_seconds must be >= 5")
    require(
        mkt.warmup_candles >= strat.warmup_bars,
        f"market.warmup_candles must be >= strategy warmup ({strat.warmup_bars})",
    )
    require(mkt.reconnect_max_backoff_seconds >= 1, "market.reconnect_max_backoff_seconds must be >= 1")
    require(mkt.queue_size >= 100, "market.queue_size must be >= 100")

    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))


def load_config(
    profile: str | None = None,
    overrides: list[str] | None = None,
    config_path: Path | None = None,
    environ: dict[str, str] | None = None,
) -> AppConfig:
    """Load, merge and validate the configuration. Raises ConfigError on any problem."""
    env = os.environ if environ is None else environ
    data = _read_toml(config_path or DEFAULT_CONFIG_PATH)

    profile = profile or env.get("TB_PROFILE") or "default"
    if profile != "default":
        if not profile.replace("_", "").replace("-", "").isalnum():
            raise ConfigError(f"Invalid profile name {profile!r}")
        data = _deep_merge(data, _read_toml(PROFILE_DIR / f"{profile}.toml"))

    for key, value in env.items():
        if key.startswith("TB_") and "__" in key:
            section, _, name = key[3:].partition("__")
            _apply_override(data, f"{section}.{name}", value)
    for item in overrides or []:
        if "=" not in item:
            raise ConfigError(f"Override must look like section.key=value, got {item!r}")
        dotted, _, raw = item.partition("=")
        _apply_override(data, dotted, raw)

    _check_no_secrets(data)
    unknown = set(data) - set(_SECTIONS) - {"symbols"}
    if unknown:
        raise ConfigError(f"Unknown config section(s): {sorted(unknown)}")

    sections = {name: _build_section(name, cls, data.get(name, {})) for name, cls in _SECTIONS.items()}
    cfg = AppConfig(**sections, symbols=_build_symbols(data.get("symbols", {})), profile=profile)
    _validate(cfg)
    return cfg
