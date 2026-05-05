from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from quant_strategy.config import load_config
from quant_strategy.data import load_market_data
from quant_strategy.optimization import candidates_to_frame, grid_search, render_config_toml


def _parse_int_list(raw: str) -> list[int]:
    return [int(value.strip()) for value in raw.split(",") if value.strip()]


def _parse_float_list(raw: str) -> list[float]:
    return [float(value.strip()) for value in raw.split(",") if value.strip()]


def _build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a grid search to optimize the dual-momentum strategy.")
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "configs" / "daily_dual_momentum.toml"),
        help="Path to the base TOML config file.",
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Optional CSV override for the data path in the config.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "strategy_optimization"),
        help="Directory for leaderboard and best-config artifacts.",
    )
    parser.add_argument(
        "--objective",
        default="sharpe",
        help="Metric used to rank parameter combinations.",
    )
    parser.add_argument(
        "--top-n-values",
        default="2,3,4",
        help="Comma-separated values for strategy.top_n.",
    )
    parser.add_argument(
        "--trend-ma-values",
        default="100,150,200",
        help="Comma-separated values for strategy.trend_ma_days.",
    )
    parser.add_argument(
        "--absolute-momentum-values",
        default="126,189,252",
        help="Comma-separated values for strategy.absolute_momentum_lookback.",
    )
    parser.add_argument(
        "--target-vol-values",
        default="0.08,0.10,0.12",
        help="Comma-separated values for risk.target_annual_vol.",
    )
    parser.add_argument(
        "--regime-gross-values",
        default="0.25,0.5,0.75",
        help="Comma-separated values for risk.regime_gross_multiplier.",
    )
    parser.add_argument("--train-start", default=None, help="Optional training period start date in YYYY-MM-DD.")
    parser.add_argument("--train-end", default=None, help="Optional training period end date in YYYY-MM-DD.")
    parser.add_argument("--test-start", default=None, help="Optional test period start date in YYYY-MM-DD.")
    parser.add_argument("--test-end", default=None, help="Optional test period end date in YYYY-MM-DD.")
    parser.add_argument("--top-k", type=int, default=10, help="How many ranked rows to print to stdout.")
    return parser


def main() -> None:
    parser = _build_argument_parser()
    args = parser.parse_args()

    config = load_config(args.config)
    if args.data:
        config = replace(config, data=replace(config.data, path=Path(args.data).resolve()))

    market_data = load_market_data(config.data.path)
    candidates = grid_search(
        market_data,
        config,
        objective=args.objective,
        top_n_values=_parse_int_list(args.top_n_values),
        trend_ma_values=_parse_int_list(args.trend_ma_values),
        absolute_momentum_values=_parse_int_list(args.absolute_momentum_values),
        target_vol_values=_parse_float_list(args.target_vol_values),
        regime_gross_values=_parse_float_list(args.regime_gross_values),
        train_start=args.train_start,
        train_end=args.train_end,
        test_start=args.test_start,
        test_end=args.test_end,
    )

    if not candidates:
        raise SystemExit("No optimization candidates were generated")

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    leaderboard_path = output_dir / "leaderboard.csv"
    leaderboard = candidates_to_frame(candidates)
    leaderboard.to_csv(leaderboard_path, index=False)

    best_candidate = candidates[0]
    best_config = replace(
        best_candidate.config,
        output=replace(best_candidate.config.output, directory=output_dir / "best_backtest"),
        config_path=output_dir / "best_config.toml",
    )
    best_config_path = output_dir / "best_config.toml"
    best_config_path.write_text(render_config_toml(best_config), encoding="utf-8")

    summary = {
        "objective": args.objective,
        "train_start": args.train_start,
        "train_end": args.train_end,
        "test_start": args.test_start,
        "test_end": args.test_end,
        "grid": {
            "top_n_values": _parse_int_list(args.top_n_values),
            "trend_ma_values": _parse_int_list(args.trend_ma_values),
            "absolute_momentum_values": _parse_int_list(args.absolute_momentum_values),
            "target_vol_values": _parse_float_list(args.target_vol_values),
            "regime_gross_values": _parse_float_list(args.regime_gross_values),
        },
        "best_parameters": {
            "top_n": best_candidate.config.strategy.top_n,
            "trend_ma_days": best_candidate.config.strategy.trend_ma_days,
            "absolute_momentum_lookback": best_candidate.config.strategy.absolute_momentum_lookback,
            "target_annual_vol": best_candidate.config.risk.target_annual_vol,
            "regime_gross_multiplier": best_candidate.config.risk.regime_gross_multiplier,
        },
        "best_train_metrics": best_candidate.train_metrics,
        "best_test_metrics": best_candidate.test_metrics,
        "leaderboard_path": str(leaderboard_path),
        "best_config_path": str(best_config_path),
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print("Strategy optimization complete")
    print(f"Data: {config.data.path}")
    print(f"Output: {output_dir}")
    print(f"Objective: {args.objective}")
    print("Best parameters:")
    for key, value in summary["best_parameters"].items():
        print(f"  {key}: {value}")
    print("Best training metrics:")
    for key, value in best_candidate.train_metrics.items():
        print(f"  {key}: {value:.6f}")
    if best_candidate.test_metrics is not None:
        print("Best test metrics:")
        for key, value in best_candidate.test_metrics.items():
            print(f"  {key}: {value:.6f}")
    print("Top ranked candidates:")
    print(leaderboard.head(args.top_k).to_string(index=False))


if __name__ == "__main__":
    main()
