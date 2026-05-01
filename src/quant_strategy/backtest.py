from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_strategy.config import BacktestConfig
from quant_strategy.data import MarketData
from quant_strategy.metrics import compute_metrics
from quant_strategy.strategy import build_target_weights


@dataclass(frozen=True)
class BacktestResult:
    """Artifacts produced by a completed backtest run."""

    target_weights: pd.DataFrame
    live_weights: pd.DataFrame
    returns: pd.Series
    costs: pd.Series
    turnover: pd.Series
    equity_curve: pd.Series
    metrics: dict[str, float]


def run_backtest(market_data: MarketData, config: BacktestConfig) -> BacktestResult:
    """Run a close-to-close backtest with one-bar-delayed weights and flat trading costs."""

    target_weights = build_target_weights(market_data.close, config)
    asset_returns = market_data.close.pct_change().fillna(0.0)

    # Shift weights forward by one bar so signals formed today trade starting tomorrow.
    live_weights = target_weights.shift(1).fillna(0.0)
    live_weights = live_weights.where(market_data.close.notna(), 0.0)

    turnover = live_weights.diff().abs().sum(axis=1)
    if not turnover.empty:
        turnover.iloc[0] = float(live_weights.iloc[0].abs().sum())

    # Trading costs are modeled as a flat bps charge on daily turnover.
    cost_rate = (config.execution.commission_bps + config.execution.slippage_bps) / 10_000.0
    costs = turnover * cost_rate

    gross_returns = (live_weights * asset_returns).sum(axis=1)
    net_returns = gross_returns - costs
    equity_curve = net_returns.add(1.0).cumprod()

    metrics = compute_metrics(net_returns, equity_curve, turnover, live_weights)

    return BacktestResult(
        target_weights=target_weights,
        live_weights=live_weights,
        returns=net_returns,
        costs=costs,
        turnover=turnover,
        equity_curve=equity_curve,
        metrics=metrics,
    )
