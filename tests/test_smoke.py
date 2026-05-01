from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_strategy.backtest import run_backtest
from quant_strategy.config import (
    BacktestConfig,
    DataConfig,
    ExecutionConfig,
    OutputConfig,
    RiskConfig,
    StrategyConfig,
)
from quant_strategy.data import load_market_data


class BacktestSmokeTest(unittest.TestCase):
    def test_backtest_runs_on_synthetic_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            csv_path = temp_dir / "prices.csv"

            dates = pd.bdate_range("2020-01-01", periods=450)
            rng = np.random.default_rng(42)
            frames = []
            for ticker, drift in {"AAA": 0.10, "BBB": 0.07, "CCC": 0.04, "DDD": 0.02}.items():
                shocks = rng.normal(0.0, 0.15 / np.sqrt(252.0), len(dates))
                close = 100.0 * np.exp(np.cumsum(drift / 252.0 + shocks))
                frames.append(
                    pd.DataFrame(
                        {
                            "date": dates,
                            "ticker": ticker,
                            "close": close,
                        }
                    )
                )

            pd.concat(frames, ignore_index=True).to_csv(csv_path, index=False)

            config = BacktestConfig(
                data=DataConfig(path=csv_path),
                strategy=StrategyConfig(
                    lookback_days=(63, 126, 252),
                    signal_weights=(0.2, 0.3, 0.5),
                    top_n=2,
                    trend_ma_days=100,
                    absolute_momentum_lookback=126,
                    rebalance_frequency="M",
                    min_history_days=180,
                ),
                risk=RiskConfig(
                    vol_lookback_days=20,
                    covariance_lookback_days=40,
                    target_annual_vol=0.10,
                    max_weight=0.60,
                    max_gross=1.00,
                    benchmark_ticker="AAA",
                    benchmark_trend_ma_days=100,
                    cash_when_benchmark_below_trend=True,
                    regime_gross_multiplier=0.25,
                ),
                execution=ExecutionConfig(commission_bps=1.0, slippage_bps=5.0),
                output=OutputConfig(directory=temp_dir / "outputs"),
                config_path=temp_dir / "config.toml",
            )

            market_data = load_market_data(csv_path)
            result = run_backtest(market_data, config)

            self.assertFalse(result.equity_curve.empty)
            self.assertIn("cagr", result.metrics)
            self.assertTrue(np.isfinite(result.metrics["max_drawdown"]))
            self.assertGreaterEqual(float(result.target_weights.abs().sum(axis=1).max()), 0.0)


if __name__ == "__main__":
    unittest.main()
