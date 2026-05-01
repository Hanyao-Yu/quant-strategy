from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "sample_prices.csv"

ASSETS = {
    "SPY": {"drift": 0.09, "vol": 0.17, "crisis_beta": 1.0},
    "QQQ": {"drift": 0.12, "vol": 0.24, "crisis_beta": 1.2},
    "IWM": {"drift": 0.08, "vol": 0.23, "crisis_beta": 1.1},
    "VNQ": {"drift": 0.07, "vol": 0.20, "crisis_beta": 1.0},
    "GLD": {"drift": 0.05, "vol": 0.15, "crisis_beta": -0.3},
    "TLT": {"drift": 0.04, "vol": 0.14, "crisis_beta": -0.6},
}


def _asset_frame(ticker: str, seed: int, dates: pd.DatetimeIndex, spec: dict[str, float]) -> pd.DataFrame:
    """Generate one synthetic daily price path with a few stylized market regimes."""

    rng = np.random.default_rng(seed)
    periods = len(dates)

    # Add smooth cyclical structure on top of random shocks so the sample data is less trivial.
    cyclical = 0.00025 * np.sin(np.linspace(0.0, 8.0 * np.pi, periods))
    seasonal = 0.00015 * np.cos(np.linspace(0.0, 5.0 * np.pi, periods))
    shocks = rng.normal(0.0, spec["vol"] / np.sqrt(252.0), periods)

    # Introduce a rough drawdown and recovery regime to make the backtest outputs more realistic.
    crisis = np.zeros(periods)
    crisis[(dates >= "2022-01-03") & (dates <= "2022-10-31")] -= 0.0016 * spec["crisis_beta"]
    crisis[(dates >= "2023-01-03") & (dates <= "2023-08-31")] += 0.0008 * spec["crisis_beta"]

    daily_returns = spec["drift"] / 252.0 + cyclical + seasonal + crisis + shocks
    close = 100.0 * np.exp(np.cumsum(daily_returns))

    # Build a plausible open series by perturbing the previous close overnight.
    overnight = rng.normal(0.0, spec["vol"] / np.sqrt(252.0) * 0.25, periods)
    previous_close = np.concatenate(([100.0], close[:-1]))
    open_ = previous_close * np.exp(overnight)
    volume = rng.integers(900_000, 8_500_000, periods)

    return pd.DataFrame(
        {
            "date": dates,
            "ticker": ticker,
            "open": open_.round(4),
            "close": close.round(4),
            "volume": volume,
        }
    )


def main() -> None:
    """Write a reusable sample CSV for local backtest demos and smoke tests."""

    dates = pd.bdate_range("2018-01-01", "2025-12-31")
    frames = [
        _asset_frame(ticker, seed, dates, spec)
        for seed, (ticker, spec) in enumerate(ASSETS.items(), start=7)
    ]

    dataset = pd.concat(frames, ignore_index=True).sort_values(["date", "ticker"])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(OUTPUT_PATH, index=False)

    print(f"Wrote {len(dataset)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
