from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class MarketData:
    """Wide matrices used by the backtest engine."""

    close: pd.DataFrame
    open_: pd.DataFrame
    volume: pd.DataFrame | None


def load_market_data(path: str | Path) -> MarketData:
    """Read the long-form CSV input and convert it into aligned market data tables."""

    csv_path = Path(path)
    frame = pd.read_csv(csv_path)

    # Normalize column names so the loader is tolerant of minor CSV formatting differences.
    frame.columns = [column.strip().lower() for column in frame.columns]

    close_column = "close" if "close" in frame.columns else "adj_close"
    required = {"date", "ticker", close_column}
    missing = required.difference(frame.columns)
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise ValueError(f"Input data is missing required columns: {missing_names}")

    frame = frame.rename(columns={close_column: "close"})
    frame["date"] = pd.to_datetime(frame["date"], utc=False)
    frame["ticker"] = frame["ticker"].astype(str).str.upper().str.strip()
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")

    optional_columns = {"open", "volume"}
    for column in optional_columns.intersection(frame.columns):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["date", "ticker", "close"])
    frame = frame.drop_duplicates(subset=["date", "ticker"], keep="last")
    frame = frame.sort_values(["date", "ticker"])

    # Pivot into date x ticker matrices, which makes vectorized backtesting straightforward.
    close = frame.pivot(index="date", columns="ticker", values="close").sort_index()
    open_ = (
        frame.pivot(index="date", columns="ticker", values="open").sort_index()
        if "open" in frame.columns
        # Fall back to close prices when open is unavailable so downstream code has a full matrix.
        else close.copy()
    )
    volume = (
        frame.pivot(index="date", columns="ticker", values="volume").sort_index()
        if "volume" in frame.columns
        else None
    )

    close.columns.name = None
    open_.columns.name = None
    if volume is not None:
        volume.columns.name = None

    return MarketData(close=close, open_=open_, volume=volume)
