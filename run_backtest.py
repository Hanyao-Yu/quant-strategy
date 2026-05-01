from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_strategy.backtest import run_backtest
from quant_strategy.config import load_config
from quant_strategy.data import load_market_data


def _build_argument_parser() -> argparse.ArgumentParser:
    """Define the small CLI used to run the standalone backtest."""

    parser = argparse.ArgumentParser(description="Run the standalone dual-momentum backtest.")
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "configs" / "daily_dual_momentum.toml"),
        help="Path to a TOML config file.",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Optional CSV override for the data path in the config.",
    )
    return parser


def main() -> None:
    """Load inputs, run the backtest, and write the output artifacts to disk."""

    parser = _build_argument_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    if args.data:
        # Allow one-off data experiments without editing the TOML file.
        config = replace(config, data=replace(config.data, path=Path(args.data).resolve()))

    market_data = load_market_data(config.data.path)
    result = run_backtest(market_data, config)

    output_dir = config.output.directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Persist the main time series outputs in separate files so they are easy to inspect.
    equity_frame = pd.DataFrame(
        {
            "equity": result.equity_curve,
            "returns": result.returns,
            "turnover": result.turnover,
            "costs": result.costs,
        }
    )
    equity_frame.to_csv(output_dir / "equity_curve.csv", index_label="date")
    result.target_weights.to_csv(output_dir / "target_weights.csv", index_label="date")
    result.live_weights.to_csv(output_dir / "live_weights.csv", index_label="date")

    # Rebalances are sparse, so exporting only change dates keeps the file compact.
    rebalances = result.target_weights.diff().fillna(result.target_weights)
    rebalances = rebalances.loc[rebalances.abs().sum(axis=1) > 0]
    rebalances.to_csv(output_dir / "rebalances.csv", index_label="date")

    metrics_payload = {
        "config_path": str(config.config_path),
        "data_path": str(config.data.path),
        **result.metrics,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    print("Backtest complete")
    print(f"Data: {config.data.path}")
    print(f"Output: {output_dir}")
    for key, value in metrics_payload.items():
        if key.endswith("_path"):
            continue
        if isinstance(value, float):
            print(f"{key}: {value:.6f}")
        else:
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
