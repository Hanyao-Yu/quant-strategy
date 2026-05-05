# Quant Strategy Starter

This project gives you a complete, low-frequency quant trading template built around a practical starter strategy:

- Daily multi-asset dual momentum
- Monthly rebalancing
- Trend filter
- Volatility-targeted sizing
- Position caps
- Transaction cost modeling

The default assumption is deliberate: start with a rule-based, daily strategy on liquid assets before touching leverage, intraday execution, or market making.

## What The Strategy Does

The included strategy combines two ideas:

1. Relative strength: rank assets by recent performance across multiple lookback windows.
2. Absolute momentum / trend: only hold assets that are still in an uptrend.

The implementation then adds practical controls:

- Monthly rebalance cadence to reduce noise and turnover
- Inverse-volatility weights
- Target annualized volatility
- Max single-name weight cap
- Regime filter tied to a benchmark trend
- Flat slippage and commission assumptions

This exact specification is an implementation choice by this project, not a claim that it is the single best strategy. The momentum and volatility-management ideas are grounded in published research; the final combination here is an engineering inference designed to be robust and easy to extend.

## Quick Start

```bash
python3 scripts/generate_sample_data.py
python3 run_backtest.py --config configs/daily_dual_momentum_optimized.toml
```

Outputs are written to `outputs/daily_dual_momentum_optimized/`.

The repository still keeps the original baseline preset for comparison and
research:

```bash
python3 run_backtest.py --config configs/daily_dual_momentum.toml
```

Those outputs are written to `outputs/daily_dual_momentum/`.

## Strategy Optimization

You can run a basic parameter search on top of the backtest engine:

```bash
python3 run_optimization.py --config configs/daily_dual_momentum.toml
```

This writes a ranked `leaderboard.csv`, a `summary.json`, and a reusable
`best_config.toml` to `outputs/strategy_optimization/`.

The repository includes a ready-to-run sample-data optimized preset at
`configs/daily_dual_momentum_optimized.toml`, and that is the main recommended
demo entrypoint in this repository. It was selected from the default search
grid using the bundled sample dataset with `sharpe` as the objective. Treat it
as a stronger sample preset, not as a production-default claim.

On the bundled sample dataset, the baseline and optimized presets compare as
follows:

| Config | Sharpe | CAGR | Max Drawdown | Total Return |
| --- | ---: | ---: | ---: | ---: |
| `daily_dual_momentum.toml` | 0.4308 | 0.0270 | -0.1735 | 0.2471 |
| `daily_dual_momentum_optimized.toml` | 0.7188 | 0.0459 | -0.1554 | 0.4509 |

Treat these results as research scaffolding, not production truth. The safest
workflow is to optimize on a training window and judge the selected parameters
on a separate test window:

```bash
python3 run_optimization.py \
  --config configs/daily_dual_momentum.toml \
  --objective sharpe \
  --train-end 2022-12-30 \
  --test-start 2023-01-02
```

## Project Layout

```text
quant-strategy/
├── configs/
├── data/
├── scripts/
├── src/quant_strategy/
├── tests/
├── run_backtest.py
└── run_optimization.py
```

## Data Format

Input data is a CSV with at least these columns:

```text
date,ticker,close
```

Optional columns:

```text
open,high,low,volume,adj_close
```

For equities and ETFs, use adjusted prices in live research whenever your vendor provides them. If you only have `adj_close`, the loader will use it as `close`.

## Backtest Assumptions

The engine uses close-to-close returns with a one-bar delay on weights:

- Signals are formed on day `t`
- Portfolio weights become active on day `t+1`
- Costs are charged when weights change

That keeps the backtest free of look-ahead bias, but it is still a simplification. You should not treat it as execution-grade simulation.

This template does **not** model:

- Queue position
- Partial fills
- Borrow availability
- Financing costs
- Corporate action handling beyond whatever is already embedded in your input prices
- Venue-specific order routing

## Recommended Workflow

1. Replace the sample CSV with real daily data for a liquid universe.
2. Start with ETFs or highly liquid large caps.
3. Validate on walk-forward splits, not one global backtest.
4. Stress turnover, slippage, and universe changes.
5. Paper trade before live capital.

## Why This Starting Point

The default design follows a conservative research path:

- Momentum / trend ideas are widely documented across assets and horizons.
- Volatility management can improve risk-adjusted behavior.
- Overfitting is a real risk, so the strategy keeps a small number of transparent rules.
- Live execution differs from backtest execution, so the template charges explicit costs and keeps frequency low.

## Research References

These sources support the major design choices:

- Time-series momentum: https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- Dual momentum intuition: https://ssrn.com/abstract=2042750
- Volatility management: https://www.nber.org/papers/w22208
- Backtest overfitting risk: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Order type / execution caveats: https://www.investor.gov/introduction-markets/how-markets-work/types-orders
- Execution slippage and routing caveats: https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work/executing-order

## Next Extensions

Good next steps after this template works on real data:

- Add walk-forward optimization
- Add benchmark-relative reporting
- Add portfolio constraints by sector or asset class
- Add broker adapter for paper trading
- Switch from flat slippage to spread-aware cost models
