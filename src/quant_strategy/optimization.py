from __future__ import annotations

from dataclasses import dataclass, replace
import math
from pathlib import Path

import pandas as pd

from quant_strategy.backtest import run_backtest
from quant_strategy.config import BacktestConfig
from quant_strategy.data import MarketData


@dataclass(frozen=True)
class OptimizationCandidate:
    """One parameter combination evaluated during strategy optimization."""

    config: BacktestConfig
    objective: str
    objective_score: float
    train_metrics: dict[str, float]
    test_metrics: dict[str, float] | None


def _slice_frame(frame: pd.DataFrame | None, start: str | None, end: str | None) -> pd.DataFrame | None:
    if frame is None:
        return None

    result = frame
    if start is not None:
        result = result.loc[result.index >= pd.Timestamp(start)]
    if end is not None:
        result = result.loc[result.index <= pd.Timestamp(end)]
    return result


def slice_market_data(
    market_data: MarketData,
    *,
    start: str | None = None,
    end: str | None = None,
) -> MarketData:
    """Slice market data to a date window while preserving aligned matrices."""

    return MarketData(
        close=_slice_frame(market_data.close, start, end),
        open_=_slice_frame(market_data.open_, start, end),
        volume=_slice_frame(market_data.volume, start, end),
    )


def build_trial_config(
    base_config: BacktestConfig,
    *,
    top_n: int,
    trend_ma_days: int,
    absolute_momentum_lookback: int,
    target_annual_vol: float,
    regime_gross_multiplier: float,
) -> BacktestConfig:
    """Create one trial config while keeping unrelated settings unchanged."""

    min_history_days = max(
        base_config.strategy.min_history_days,
        trend_ma_days,
        absolute_momentum_lookback,
        max(base_config.strategy.lookback_days),
    )

    return replace(
        base_config,
        strategy=replace(
            base_config.strategy,
            top_n=top_n,
            trend_ma_days=trend_ma_days,
            absolute_momentum_lookback=absolute_momentum_lookback,
            min_history_days=min_history_days,
        ),
        risk=replace(
            base_config.risk,
            target_annual_vol=target_annual_vol,
            regime_gross_multiplier=regime_gross_multiplier,
        ),
    )


def _objective_score(metrics: dict[str, float], objective: str) -> float:
    if objective not in metrics:
        raise ValueError(f"Unsupported objective metric: {objective}")

    value = float(metrics[objective])
    if math.isnan(value):
        return float("-inf")

    if objective in {"annualized_volatility", "average_daily_turnover"}:
        return -value
    return value


def grid_search(
    market_data: MarketData,
    base_config: BacktestConfig,
    *,
    objective: str,
    top_n_values: list[int],
    trend_ma_values: list[int],
    absolute_momentum_values: list[int],
    target_vol_values: list[float],
    regime_gross_values: list[float],
    train_start: str | None = None,
    train_end: str | None = None,
    test_start: str | None = None,
    test_end: str | None = None,
) -> list[OptimizationCandidate]:
    """Evaluate a grid of parameter combinations and rank them by objective."""

    train_market_data = slice_market_data(market_data, start=train_start, end=train_end)
    if train_market_data.close.empty:
        raise ValueError("Training window is empty after slicing the market data")

    test_market_data: MarketData | None = None
    if test_start is not None or test_end is not None:
        test_market_data = slice_market_data(market_data, start=test_start, end=test_end)
        if test_market_data.close.empty:
            raise ValueError("Test window is empty after slicing the market data")

    candidates: list[OptimizationCandidate] = []
    for top_n in top_n_values:
        for trend_ma_days in trend_ma_values:
            for absolute_momentum_lookback in absolute_momentum_values:
                for target_annual_vol in target_vol_values:
                    for regime_gross_multiplier in regime_gross_values:
                        trial_config = build_trial_config(
                            base_config,
                            top_n=top_n,
                            trend_ma_days=trend_ma_days,
                            absolute_momentum_lookback=absolute_momentum_lookback,
                            target_annual_vol=target_annual_vol,
                            regime_gross_multiplier=regime_gross_multiplier,
                        )

                        train_result = run_backtest(train_market_data, trial_config)
                        score = _objective_score(train_result.metrics, objective)
                        test_metrics = None
                        if test_market_data is not None:
                            test_result = run_backtest(test_market_data, trial_config)
                            test_metrics = test_result.metrics

                        candidates.append(
                            OptimizationCandidate(
                                config=trial_config,
                                objective=objective,
                                objective_score=score,
                                train_metrics=train_result.metrics,
                                test_metrics=test_metrics,
                            )
                        )

    candidates.sort(key=lambda candidate: candidate.objective_score, reverse=True)
    return candidates


def candidates_to_frame(candidates: list[OptimizationCandidate]) -> pd.DataFrame:
    """Flatten optimization results into a leaderboard DataFrame."""

    rows: list[dict[str, float | int | str]] = []
    for candidate in candidates:
        row: dict[str, float | int | str] = {
            "objective": candidate.objective,
            "objective_score": candidate.objective_score,
            "top_n": candidate.config.strategy.top_n,
            "trend_ma_days": candidate.config.strategy.trend_ma_days,
            "absolute_momentum_lookback": candidate.config.strategy.absolute_momentum_lookback,
            "target_annual_vol": candidate.config.risk.target_annual_vol,
            "regime_gross_multiplier": candidate.config.risk.regime_gross_multiplier,
        }
        for key, value in candidate.train_metrics.items():
            row[f"train_{key}"] = value
        if candidate.test_metrics is not None:
            for key, value in candidate.test_metrics.items():
                row[f"test_{key}"] = value
        rows.append(row)
    return pd.DataFrame(rows)


def _toml_value(value: str | int | float | bool | Path) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Path):
        return _toml_value(str(value))
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return str(value)


def render_config_toml(config: BacktestConfig) -> str:
    """Serialize a typed config back into TOML for reuse."""

    lines = [
        "[data]",
        f"path = {_toml_value(config.data.path)}",
        "",
        "[strategy]",
        f"lookback_days = [{', '.join(str(value) for value in config.strategy.lookback_days)}]",
        f"signal_weights = [{', '.join(str(value) for value in config.strategy.signal_weights)}]",
        f"top_n = {config.strategy.top_n}",
        f"trend_ma_days = {config.strategy.trend_ma_days}",
        f"absolute_momentum_lookback = {config.strategy.absolute_momentum_lookback}",
        f"rebalance_frequency = {_toml_value(config.strategy.rebalance_frequency)}",
        f"min_history_days = {config.strategy.min_history_days}",
        "",
        "[risk]",
        f"vol_lookback_days = {config.risk.vol_lookback_days}",
        f"covariance_lookback_days = {config.risk.covariance_lookback_days}",
        f"target_annual_vol = {config.risk.target_annual_vol}",
        f"max_weight = {config.risk.max_weight}",
        f"max_gross = {config.risk.max_gross}",
        f"benchmark_ticker = {_toml_value(config.risk.benchmark_ticker or '')}",
        f"benchmark_trend_ma_days = {config.risk.benchmark_trend_ma_days}",
        f"cash_when_benchmark_below_trend = {_toml_value(config.risk.cash_when_benchmark_below_trend)}",
        f"regime_gross_multiplier = {config.risk.regime_gross_multiplier}",
        "",
        "[execution]",
        f"commission_bps = {config.execution.commission_bps}",
        f"slippage_bps = {config.execution.slippage_bps}",
        "",
        "[output]",
        f"directory = {_toml_value(config.output.directory)}",
        "",
    ]
    return "\n".join(lines)
