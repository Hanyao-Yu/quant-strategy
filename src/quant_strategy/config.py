from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class DataConfig:
    """Location of the input market data file."""

    path: Path


@dataclass(frozen=True)
class StrategyConfig:
    """Signal construction and rebalance settings."""

    lookback_days: tuple[int, ...]
    signal_weights: tuple[float, ...]
    top_n: int
    trend_ma_days: int
    absolute_momentum_lookback: int
    rebalance_frequency: str
    min_history_days: int


@dataclass(frozen=True)
class RiskConfig:
    """Risk targeting, exposure limits, and regime filter inputs."""

    vol_lookback_days: int
    covariance_lookback_days: int
    target_annual_vol: float
    max_weight: float
    max_gross: float
    benchmark_ticker: str | None
    benchmark_trend_ma_days: int
    cash_when_benchmark_below_trend: bool
    regime_gross_multiplier: float


@dataclass(frozen=True)
class ExecutionConfig:
    """Flat trading cost assumptions expressed in basis points."""

    commission_bps: float
    slippage_bps: float


@dataclass(frozen=True)
class OutputConfig:
    """Destination for backtest artifacts."""

    directory: Path


@dataclass(frozen=True)
class BacktestConfig:
    """Fully parsed configuration used by the backtest pipeline."""

    data: DataConfig
    strategy: StrategyConfig
    risk: RiskConfig
    execution: ExecutionConfig
    output: OutputConfig
    config_path: Path


def _resolve_path(base_dir: Path, raw: str) -> Path:
    """Resolve config-relative paths against the directory of the TOML file."""

    path = Path(raw)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_config(path: str | Path) -> BacktestConfig:
    """Load and validate the TOML configuration into typed dataclasses."""

    config_path = Path(path).resolve()
    doc = tomllib.loads(config_path.read_text(encoding="utf-8"))
    base_dir = config_path.parent

    # Parse strategy settings first so cross-field validation stays local.
    strategy = StrategyConfig(
        lookback_days=tuple(int(value) for value in doc["strategy"]["lookback_days"]),
        signal_weights=tuple(float(value) for value in doc["strategy"]["signal_weights"]),
        top_n=int(doc["strategy"]["top_n"]),
        trend_ma_days=int(doc["strategy"]["trend_ma_days"]),
        absolute_momentum_lookback=int(doc["strategy"]["absolute_momentum_lookback"]),
        rebalance_frequency=str(doc["strategy"]["rebalance_frequency"]).upper(),
        min_history_days=int(doc["strategy"]["min_history_days"]),
    )

    if len(strategy.lookback_days) != len(strategy.signal_weights):
        raise ValueError("strategy.lookback_days and strategy.signal_weights must have the same length")
    if strategy.rebalance_frequency not in {"D", "W", "M"}:
        raise ValueError("strategy.rebalance_frequency must be one of D, W, M")
    if strategy.top_n < 1:
        raise ValueError("strategy.top_n must be >= 1")

    risk = RiskConfig(
        vol_lookback_days=int(doc["risk"]["vol_lookback_days"]),
        covariance_lookback_days=int(doc["risk"]["covariance_lookback_days"]),
        target_annual_vol=float(doc["risk"]["target_annual_vol"]),
        max_weight=float(doc["risk"]["max_weight"]),
        max_gross=float(doc["risk"]["max_gross"]),
        benchmark_ticker=doc["risk"].get("benchmark_ticker"),
        benchmark_trend_ma_days=int(doc["risk"]["benchmark_trend_ma_days"]),
        cash_when_benchmark_below_trend=bool(doc["risk"]["cash_when_benchmark_below_trend"]),
        regime_gross_multiplier=float(doc["risk"]["regime_gross_multiplier"]),
    )

    if not 0 < risk.max_weight <= 1:
        raise ValueError("risk.max_weight must be in (0, 1]")
    if not 0 < risk.max_gross <= 1:
        raise ValueError("risk.max_gross must be in (0, 1]")
    if not 0 <= risk.regime_gross_multiplier <= 1:
        raise ValueError("risk.regime_gross_multiplier must be in [0, 1]")

    # Keep file paths relative to the config file instead of the current shell directory.
    return BacktestConfig(
        data=DataConfig(path=_resolve_path(base_dir, str(doc["data"]["path"]))),
        strategy=strategy,
        risk=risk,
        execution=ExecutionConfig(
            commission_bps=float(doc["execution"]["commission_bps"]),
            slippage_bps=float(doc["execution"]["slippage_bps"]),
        ),
        output=OutputConfig(directory=_resolve_path(base_dir, str(doc["output"]["directory"]))),
        config_path=config_path,
    )
