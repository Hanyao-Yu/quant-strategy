# Quant Strategy Starter 中文说明

这个项目提供了一个完整的低频量化交易模板，围绕一个实用的入门策略构建：

- 日频多资产双动量
- 月度再平衡
- 趋势过滤
- 波动率目标仓位
- 单个标的权重上限
- 交易成本建模

项目的默认思路是有意保持克制：先从规则清晰、低频、流动性好的资产开始，再考虑杠杆、日内执行或更复杂的做市策略。

## 策略做了什么

内置策略结合了两个核心思想：

1. 相对强弱：按多个回看窗口的历史表现对资产进行排序。
2. 绝对动量 / 趋势：只持有仍处于上升趋势中的资产。

在此基础上，项目又加入了更贴近实盘研究的控制项：

- 使用月度再平衡以降低噪声和换手
- 使用逆波动率进行基础权重分配
- 控制目标年化波动率
- 限制单个标的最大权重
- 使用基准趋势进行市场状态过滤
- 显式计入滑点和手续费

这里的具体实现是本项目的工程化选择，不代表它是“最佳策略”。动量和波动率管理的思路有研究支持，但当前组合方式更强调稳健、透明和易扩展。

## 快速开始

```bash
python3 scripts/generate_sample_data.py
python3 run_backtest.py --config configs/daily_dual_momentum.toml
```

输出结果会写入 `outputs/daily_dual_momentum/`。

## 项目结构

```text
quant-strategy/
├── configs/
├── data/
├── scripts/
├── src/quant_strategy/
├── tests/
└── run_backtest.py
```

## 运行要求

- Python 3.11 或更高版本
- 依赖见 `pyproject.toml`

推荐安装方式：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## 数据格式

输入数据为 CSV，至少需要以下列：

```text
date,ticker,close
```

可选列：

```text
open,high,low,volume,adj_close
```

对于股票和 ETF，如果数据供应商提供复权价格，建议在研究和实盘准备中使用复权数据。若只有 `adj_close`，加载器会自动将其作为 `close` 使用。

## 回测假设

回测引擎使用收盘到收盘收益，并采用一根 bar 延迟生效的权重：

- 在 `t` 日收盘后生成信号
- 组合权重从 `t+1` 开始生效
- 当权重发生变化时计入交易成本

这样可以避免明显的未来函数问题，但它仍然只是简化后的回测模型，不能视为可直接上线的执行级模拟。

当前模板**没有**覆盖以下现实问题：

- 排队成交顺序
- 部分成交
- 融券可用性
- 融资成本
- 除输入价格中已隐含部分外的公司行为处理
- 不同交易场所的路由差异

## 推荐工作流

1. 用真实的日频数据替换示例 CSV。
2. 先从 ETF 或流动性较好的大盘股开始。
3. 使用 walk-forward 切分验证，而不是只看一次全样本回测。
4. 对换手、滑点和股票池变化做压力测试。
5. 先做模拟盘，再考虑真实资金。

## 为什么选择这个起点

这个默认设计遵循一个相对保守的研究路径：

- 动量 / 趋势类思路在多个资产类别和时间尺度上都有较多研究支持。
- 波动率管理有机会改善风险调整后表现。
- 过拟合是真实风险，因此策略规则保持少而透明。
- 实盘执行和回测执行差异很大，所以模板显式加入成本并保持较低频率。

## 研究参考

以下资料支持本项目中的主要设计选择：

- Time-series momentum: https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum
- Dual momentum intuition: https://ssrn.com/abstract=2042750
- Volatility management: https://www.nber.org/papers/w22208
- Backtest overfitting risk: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253
- Order type / execution caveats: https://www.investor.gov/introduction-markets/how-markets-work/types-orders
- Execution slippage and routing caveats: https://www.investor.gov/introduction-investing/investing-basics/how-stock-markets-work/executing-order

## 后续可扩展方向

当你确认这个模板能在真实数据上稳定运行后，可以继续考虑：

- 增加 walk-forward 参数优化
- 增加相对基准的绩效报告
- 增加行业或资产类别约束
- 增加对接券商或模拟交易接口
- 将固定滑点模型替换为更贴近市场点差的成本模型
