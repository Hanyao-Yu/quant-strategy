from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_strategy.config import (
    BacktestConfig,
    DataConfig,
    ExecutionConfig,
    OutputConfig,
    RiskConfig,
    StrategyConfig,
)
from quant_strategy.data import load_market_data
from quant_strategy.optimization import candidates_to_frame, grid_search, render_config_toml


class OptimizationTest(unittest.TestCase):
    def test_grid_search_returns_ranked_candidates_and_serializable_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            csv_path = temp_dir / "prices.csv"

            dates = pd.bdate_range("2020-01-01", periods=500)
            rng = np.random.default_rng(7)
            frames = []
            for ticker, drift in {"AAA": 0.12, "BBB": 0.08, "CCC": 0.04, "DDD": 0.01}.items():
                shocks = rng.normal(0.0, 0.14 / np.sqrt(252.0), len(dates))
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
                    top_n=3,
                    trend_ma_days=150,
                    absolute_momentum_lookback=126,
                    rebalance_frequency="M",
                    min_history_days=260,
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
                    regime_gross_multiplier=0.5,
                ),
                execution=ExecutionConfig(commission_bps=1.0, slippage_bps=5.0),
                output=OutputConfig(directory=temp_dir / "outputs"),
                config_path=temp_dir / "config.toml",
            )

            market_data = load_market_data(csv_path)
            candidates = grid_search(
                market_data,
                config,
                objective="sharpe",
                top_n_values=[2, 3],
                trend_ma_values=[100, 150],
                absolute_momentum_values=[126],
                target_vol_values=[0.08, 0.10],
                regime_gross_values=[0.5],
                train_end="2021-06-30",
                test_start="2021-07-01",
            )

            self.assertEqual(len(candidates), 8)
            self.assertGreaterEqual(candidates[0].objective_score, candidates[-1].objective_score)
            self.assertIsNotNone(candidates[0].test_metrics)

            leaderboard = candidates_to_frame(candidates)
            self.assertIn("objective_score", leaderboard.columns)
            self.assertIn("train_sharpe", leaderboard.columns)
            self.assertIn("test_sharpe", leaderboard.columns)

            best_config = replace(
                candidates[0].config,
                output=replace(candidates[0].config.output, directory=temp_dir / "best_backtest"),
            )
            config_toml = render_config_toml(best_config)
            self.assertIn("[strategy]", config_toml)
            self.assertIn("top_n =", config_toml)
            self.assertIn("directory =", config_toml)


if __name__ == "__main__":
    unittest.main()
