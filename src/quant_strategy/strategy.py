from __future__ import annotations

import numpy as np
import pandas as pd

from quant_strategy.config import BacktestConfig


def _cross_sectional_zscore(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardize each date across assets so lookbacks can be blended cleanly."""

    mean = frame.mean(axis=1)
    std = frame.std(axis=1, ddof=0).replace(0.0, np.nan)
    return frame.sub(mean, axis=0).div(std, axis=0).fillna(0.0)


def _rebalance_mask(index: pd.DatetimeIndex, frequency: str) -> pd.Series:
    """Mark which dates are eligible for rebalancing."""

    marker = pd.Series(True, index=index)
    if frequency == "D":
        return marker
    if frequency == "W":
        dates = marker.groupby(index.to_period("W-FRI")).tail(1).index
    elif frequency == "M":
        dates = marker.groupby(index.to_period("M")).tail(1).index
    else:
        raise ValueError(f"Unsupported rebalance frequency: {frequency}")
    rebalance = pd.Series(False, index=index)
    rebalance.loc[dates] = True
    return rebalance


def _cap_weights(weights: pd.Series, cap: float, total: float) -> pd.Series:
    """Iteratively cap position sizes while preserving the requested gross exposure."""

    if weights.empty or total <= 0:
        return pd.Series(dtype=float)

    weights = weights[weights > 0].copy()
    if weights.empty:
        return pd.Series(dtype=float)

    remaining = float(total)
    free = weights / weights.sum()
    capped = pd.Series(0.0, index=weights.index)

    while not free.empty and remaining > 0:
        scaled = free / free.sum() * remaining
        over_cap = scaled > cap + 1e-12
        if not over_cap.any():
            capped = capped.add(scaled, fill_value=0.0)
            break

        capped_names = scaled[over_cap].index
        capped.loc[capped_names] = cap
        remaining = float(total - capped.sum())
        free = free.drop(capped_names)

    return capped[capped > 0]


def _portfolio_volatility(weights: pd.Series, returns_window: pd.DataFrame) -> float:
    """Estimate annualized portfolio volatility from a rolling covariance window."""

    if weights.empty:
        return 0.0

    if returns_window.empty or len(returns_window) < 2:
        return 0.0

    covariance = returns_window.cov() * 252.0
    vector = weights.reindex(covariance.index).fillna(0.0).to_numpy()
    variance = float(vector.T @ covariance.to_numpy() @ vector)
    return float(np.sqrt(max(variance, 0.0)))


def build_target_weights(close: pd.DataFrame, config: BacktestConfig) -> pd.DataFrame:
    """Build end-of-day target weights for the dual-momentum strategy."""

    close = close.sort_index().astype(float)
    returns = close.pct_change()

    # Blend multiple lookback horizons into one cross-sectional momentum score.
    score = pd.DataFrame(0.0, index=close.index, columns=close.columns)
    for lookback, signal_weight in zip(config.strategy.lookback_days, config.strategy.signal_weights, strict=True):
        lookback_returns = close.div(close.shift(lookback)).sub(1.0)
        score = score.add(_cross_sectional_zscore(lookback_returns).mul(signal_weight), fill_value=0.0)

    # Asset-level filters and risk inputs are computed once, then sampled on rebalance dates.
    trend_filter = close.gt(close.rolling(config.strategy.trend_ma_days).mean())
    absolute_momentum = close.div(close.shift(config.strategy.absolute_momentum_lookback)).sub(1.0)
    volatility = returns.rolling(config.risk.vol_lookback_days).std(ddof=0).mul(np.sqrt(252.0))
    rebalances = _rebalance_mask(close.index, config.strategy.rebalance_frequency)

    # Wait until every rolling input has enough history before allowing a rebalance.
    minimum_history = max(
        config.strategy.min_history_days,
        config.strategy.trend_ma_days,
        config.strategy.absolute_momentum_lookback,
        max(config.strategy.lookback_days),
        config.risk.covariance_lookback_days + 1,
    )

    weights = pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    benchmark = config.risk.benchmark_ticker
    benchmark_available = benchmark in close.columns if benchmark else False
    benchmark_trend = (
        close[benchmark].rolling(config.risk.benchmark_trend_ma_days).mean()
        if benchmark_available
        else None
    )

    for index_position, date in enumerate(close.index):
        if index_position < minimum_history or not rebalances.loc[date]:
            continue

        # Rebalance dates should overwrite the prior holdings. Start from cash,
        # then fill selected positions if any assets pass the filters.
        weights.loc[date] = 0.0

        current_close = close.loc[date]
        current_score = score.loc[date]
        current_trend = trend_filter.loc[date]
        current_abs_momentum = absolute_momentum.loc[date]
        current_volatility = volatility.loc[date]

        # Only rank names with complete data, positive absolute momentum, and an active trend.
        eligible = (
            current_close.notna()
            & current_score.notna()
            & current_trend.fillna(False)
            & current_abs_momentum.gt(0).fillna(False)
            & current_volatility.notna()
        )

        ranked = current_score[eligible].sort_values(ascending=False)
        selected = ranked.head(config.strategy.top_n)
        if selected.empty:
            continue

        selected_volatility = current_volatility[selected.index].clip(lower=1e-6)
        inverse_volatility = 1.0 / selected_volatility
        base_weights = inverse_volatility / inverse_volatility.sum()

        # Scale gross exposure down if the selected basket is already too volatile.
        returns_window = (
            returns[selected.index]
            .loc[:date]
            .tail(config.risk.covariance_lookback_days)
            .dropna(how="any")
        )
        base_volatility = _portfolio_volatility(base_weights, returns_window)

        target_gross = config.risk.max_gross
        if base_volatility > 0:
            target_gross = min(config.risk.max_gross, config.risk.target_annual_vol / base_volatility)

        # Optional regime filter: de-risk when the benchmark is below its long-term trend.
        if (
            config.risk.cash_when_benchmark_below_trend
            and benchmark_available
            and benchmark_trend is not None
            and pd.notna(close.at[date, benchmark])
            and pd.notna(benchmark_trend.at[date])
            and close.at[date, benchmark] <= benchmark_trend.at[date]
        ):
            target_gross *= config.risk.regime_gross_multiplier

        # Apply per-name caps while keeping as much of the requested gross exposure as feasible.
        feasible_total = min(target_gross, len(selected.index) * config.risk.max_weight)
        final_weights = _cap_weights(base_weights, config.risk.max_weight, feasible_total)
        if final_weights.empty:
            continue

        weights.loc[date, final_weights.index] = final_weights

    # Persist holdings between rebalance dates and flatten symbols with missing prices.
    weights = weights.ffill().fillna(0.0)
    weights = weights.where(close.notna(), 0.0)
    return weights
