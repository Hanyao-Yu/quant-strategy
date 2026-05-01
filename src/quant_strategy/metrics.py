from __future__ import annotations

import math

import pandas as pd


def compute_metrics(
    returns: pd.Series,
    equity_curve: pd.Series,
    turnover: pd.Series,
    live_weights: pd.DataFrame,
) -> dict[str, float]:
    """Compute a compact set of portfolio-level performance diagnostics."""

    if returns.empty:
        return {}

    periods = len(returns)
    years = periods / 252.0
    ending_value = float(equity_curve.iloc[-1]) if not equity_curve.empty else 1.0
    total_return = ending_value - 1.0
    cagr = ending_value ** (1.0 / years) - 1.0 if years > 0 and ending_value > 0 else float("nan")

    annualized_volatility = float(returns.std(ddof=0) * math.sqrt(252.0))
    sharpe = (
        float(returns.mean() / returns.std(ddof=0) * math.sqrt(252.0))
        if returns.std(ddof=0) > 0
        else float("nan")
    )

    # Drawdown is measured relative to the running peak of the equity curve.
    drawdown = equity_curve.div(equity_curve.cummax()).sub(1.0)
    max_drawdown = float(drawdown.min()) if not drawdown.empty else float("nan")
    calmar = cagr / abs(max_drawdown) if max_drawdown < 0 else float("nan")

    gross_exposure = live_weights.abs().sum(axis=1)

    return {
        "total_return": float(total_return),
        "cagr": float(cagr),
        "annualized_volatility": annualized_volatility,
        "sharpe": float(sharpe),
        "max_drawdown": max_drawdown,
        "calmar": float(calmar),
        "average_daily_turnover": float(turnover.mean()),
        "average_gross_exposure": float(gross_exposure.mean()),
        "positive_day_ratio": float((returns > 0).mean()),
    }
