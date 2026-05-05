"""
回测可视化: 权益曲线、回撤、月度收益柱状图
需安装: matplotlib
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from backtest.metrics import max_drawdown


def save_report_charts(
    result: dict,
    candles: list[dict],
    out_dir: str,
    *,
    prefix: str = "report",
) -> list[str]:
    """
    根据 run_backtest(..., include_equity_curve=True) 的结果出图。
    返回已写入的文件路径列表。
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise RuntimeError("请先安装 matplotlib: pip install matplotlib") from e

    eq = result.get("equity_curve")
    if not eq or len(eq) != len(candles):
        raise ValueError("result 需包含与 candles 等长的 equity_curve")

    os.makedirs(out_dir, exist_ok=True)
    ts = [datetime.fromtimestamp(c["timestamp"], tz=timezone.utc) for c in candles]
    equity = list(eq)

    paths: list[str] = []

    # 1) 权益 + 回撤
    peak = equity[0]
    dd_series: list[float] = []
    for x in equity:
        peak = max(peak, x)
        dd_series.append((peak - x) / peak * 100.0 if peak else 0.0)

    fig, ax1 = plt.subplots(figsize=(11, 5))
    ax1.plot(ts, equity, color="#1f77b4", label="Equity")
    ax1.set_ylabel("Equity (USDT)")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.fill_between(ts, dd_series, color="#d62728", alpha=0.25, label="Drawdown %")
    ax2.set_ylabel("Drawdown %")

    fig.suptitle(
        f"{result.get('strategy','')} | PnL {result.get('profit_pct',0):+.2f}% | "
        f"MaxDD {max_drawdown(equity)*100:.2f}%"
    )
    fig.autofmt_xdate()
    fig.tight_layout()
    p1 = os.path.join(out_dir, f"{prefix}_equity_dd.png")
    fig.savefig(p1, dpi=120)
    plt.close(fig)
    paths.append(p1)

    # 2) 月度收益 (按自然月最后一条 K 的权益环比)
    month_last_idx: dict[tuple[int, int], int] = {}
    for i, t in enumerate(ts):
        k = (t.year, t.month)
        month_last_idx[k] = i

    months_sorted = sorted(month_last_idx.keys())
    monthly_returns: list[float] = []
    month_labels: list[str] = []
    prev_eq: float | None = None
    for ym in months_sorted:
        idx = month_last_idx[ym]
        e = equity[idx]
        if prev_eq is not None and prev_eq > 0:
            monthly_returns.append((e / prev_eq - 1.0) * 100.0)
            month_labels.append(f"{ym[0]}-{ym[1]:02d}")
        prev_eq = e

    if monthly_returns:
        fig2, ax = plt.subplots(figsize=(11, 4))
        colors = ["#2ca02c" if r >= 0 else "#d62728" for r in monthly_returns]
        ax.bar(month_labels, monthly_returns, color=colors)
        ax.axhline(0, color="black", linewidth=0.5)
        ax.set_ylabel("Monthly return %")
        ax.set_title("Monthly return (EoM equity)")
        plt.xticks(rotation=45, ha="right")
        fig2.tight_layout()
        p2 = os.path.join(out_dir, f"{prefix}_monthly.png")
        fig2.savefig(p2, dpi=120)
        plt.close(fig2)
        paths.append(p2)

    return paths
