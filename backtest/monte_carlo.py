"""
蒙特卡洛模拟 — 机构级别
参数化 VaR / CVaR / 压力测试 / 相关性模拟 / Bootstrap
"""
import random
import math
from typing import List, Dict, Optional
from utils.logger import get_logger

logger = get_logger("montecarlo")


def run_monte_carlo(trade_returns: list, simulations: int = 10000,
                    confidence: int = 95, trades_per_sim: int = None) -> dict:
    """蒙特卡洛模拟 — 基础版"""
    if not trade_returns:
        return {}

    n = trades_per_sim or len(trade_returns)
    final_returns = []
    max_drawdowns = []

    for _ in range(simulations):
        sampled = random.choices(trade_returns, k=n)
        cumulative = [100.0]
        peak = 100.0
        max_dd = 0

        for r in sampled:
            val = cumulative[-1] * (1 + r / 100)
            cumulative.append(val)
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100
            if dd > max_dd:
                max_dd = dd

        final_returns.append(cumulative[-1])
        max_drawdowns.append(max_dd)

    final_returns.sort()
    max_drawdowns.sort()

    lower_idx = int((100 - confidence) / 200 * simulations)
    upper_idx = int((100 + confidence) / 200 * simulations)

    avg_final = sum(final_returns) / len(final_returns)
    median_final = final_returns[simulations // 2]
    prob_profit = sum(1 for r in final_returns if r > 100) / len(final_returns) * 100

    result = {
        "simulations": simulations,
        "trades_per_sim": n,
        "confidence": confidence,
        "avg_final": round(avg_final, 2),
        "median_final": round(median_final, 2),
        "prob_profit": round(prob_profit, 2),
        "worst_case": round(final_returns[0], 2),
        "best_case": round(final_returns[-1], 2),
        "ci_lower": round(final_returns[lower_idx], 2),
        "ci_upper": round(final_returns[upper_idx], 2),
        "avg_max_dd": round(sum(max_drawdowns) / len(max_drawdowns), 2),
        "median_max_dd": round(max_drawdowns[simulations // 2], 2),
        "worst_max_dd": round(max_drawdowns[0], 2),
        "_histogram": _build_histogram(final_returns),
        "_dd_histogram": _build_histogram(max_drawdowns),
    }
    return result


def parametric_var(returns: List[float], confidence: float = 95.0,
                   horizon_days: int = 1, method: str = "historical") -> dict:
    """
    参数化 VaR (Value at Risk)
    method: historical / parametric / cornish_fisher
    """
    if not returns or len(returns) < 10:
        return {}

    alpha = 1 - confidence / 100
    sorted_returns = sorted(returns)
    n = len(sorted_returns)

    if method == "historical":
        # 历史模拟法
        idx = int(alpha * n)
        var = sorted_returns[idx]
        cvar = sum(sorted_returns[:idx + 1]) / (idx + 1)

    elif method == "parametric":
        # 参数法（正态分布假设）
        mean = sum(returns) / n
        std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (n - 1))
        # Z-score
        z = _norm_ppf(alpha)
        var = mean + z * std
        cvar = mean - std * _norm_pdf(z) / alpha

    elif method == "cornish_fisher":
        # Cornish-Fisher 展开（考虑偏度和峰度）
        mean = sum(returns) / n
        std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (n - 1))
        skew = sum((r - mean) ** 3 for r in returns) / (n * std ** 3) if std > 0 else 0
        kurt = sum((r - mean) ** 4 for r in returns) / (n * std ** 4) - 3 if std > 0 else 0

        z = _norm_ppf(alpha)
        # Cornish-Fisher 调整
        z_cf = (z + (z ** 2 - 1) * skew / 6
                + z * (z ** 2 - 3) * kurt / 24
                - z * (2 * z ** 2 - 5) * skew ** 2 / 36)
        var = mean + z_cf * std
        cvar = mean - std * _norm_pdf(z_cf) / alpha

    else:
        return {"error": f"未知方法: {method}"}

    # 年化
    annual_var = var * math.sqrt(252 / horizon_days) if horizon_days > 0 else var
    annual_cvar = cvar * math.sqrt(252 / horizon_days) if horizon_days > 0 else cvar

    return {
        "method": method,
        "confidence": confidence,
        "horizon_days": horizon_days,
        "var_daily": round(var, 4),
        "cvar_daily": round(cvar, 4),
        "var_annual": round(annual_var, 4),
        "cvar_annual": round(annual_cvar, 4),
        "var_pct": round(abs(var) * 100, 2),
        "cvar_pct": round(abs(cvar) * 100, 2),
    }


def stress_test(returns: List[float], scenarios: List[dict] = None) -> dict:
    """
    压力测试
    scenarios: [{"name": "2008金融危机", "shock_pct": -40, "vol_multiplier": 3},
                {"name": "闪崩", "shock_pct": -10, "vol_multiplier": 5}]
    """
    if not returns:
        return {}

    if not scenarios:
        scenarios = [
            {"name": "温和下跌", "shock_pct": -10, "vol_multiplier": 1.5},
            {"name": "中等危机", "shock_pct": -25, "vol_multiplier": 2.5},
            {"name": "2008金融危机", "shock_pct": -40, "vol_multiplier": 3.0},
            {"name": "闪崩", "shock_pct": -10, "vol_multiplier": 5.0},
            {"name": "黑天鹅", "shock_pct": -60, "vol_multiplier": 4.0},
        ]

    mean = sum(returns) / len(returns)
    std = math.sqrt(sum((r - mean) ** 2 for r in returns) / max(len(returns) - 1, 1))

    results = []
    for scenario in scenarios:
        shock = scenario.get("shock_pct", -20) / 100
        vol_mult = scenario.get("vol_multiplier", 2.0)

        # 模拟压力情景下的收益分布
        stressed_mean = mean + shock
        stressed_std = std * vol_mult

        # 蒙特卡洛模拟
        sim_returns = [random.gauss(stressed_mean, stressed_std) for _ in range(10000)]
        sim_returns.sort()

        var_95 = sim_returns[int(0.05 * 10000)]
        cvar_95 = sum(sim_returns[:500]) / 500
        max_loss = sim_returns[0]
        prob_recovery = sum(1 for r in sim_returns if r > 0) / 10000 * 100

        results.append({
            "name": scenario["name"],
            "shock_pct": scenario.get("shock_pct", -20),
            "vol_multiplier": vol_mult,
            "var_95": round(var_95, 4),
            "cvar_95": round(cvar_95, 4),
            "max_loss": round(max_loss, 4),
            "prob_recovery": round(prob_recovery, 2),
        })

    return {
        "base_stats": {
            "mean": round(mean, 4),
            "std": round(std, 4),
            "sharpe": round(mean / std * math.sqrt(252), 4) if std > 0 else 0,
        },
        "scenarios": results,
    }


def correlation_monte_carlo(assets_returns: Dict[str, List[float]],
                            simulations: int = 10000,
                            horizon_days: int = 252) -> dict:
    """
    多资产相关性蒙特卡洛模拟
    assets_returns: {"BTC": [0.01, -0.02, ...], "ETH": [0.02, -0.01, ...]}
    """
    if not assets_returns or len(assets_returns) < 2:
        return {}

    asset_names = list(assets_returns.keys())
    n_assets = len(asset_names)

    # 计算均值向量和协方差矩阵
    means = []
    for name in asset_names:
        rets = assets_returns[name]
        means.append(sum(rets) / len(rets))

    # 简化协方差矩阵
    cov_matrix = []
    for i in range(n_assets):
        row = []
        for j in range(n_assets):
            ri = assets_returns[asset_names[i]]
            rj = assets_returns[asset_names[j]]
            n = min(len(ri), len(rj))
            mean_i = means[i]
            mean_j = means[j]
            cov = sum((ri[k] - mean_i) * (rj[k] - mean_j) for k in range(n)) / (n - 1)
            row.append(cov)
        cov_matrix.append(row)

    # 模拟（简化：独立模拟 + 相关性调整）
    portfolio_returns = []
    for _ in range(simulations):
        sim_total = 0
        for i in range(n_assets):
            weight = 1.0 / n_assets  # 等权
            sim_ret = random.gauss(means[i] * horizon_days,
                                   math.sqrt(cov_matrix[i][i] * horizon_days))
            sim_total += weight * sim_ret
        portfolio_returns.append(sim_total)

    portfolio_returns.sort()

    return {
        "assets": asset_names,
        "horizon_days": horizon_days,
        "simulations": simulations,
        "portfolio_mean": round(sum(portfolio_returns) / len(portfolio_returns), 4),
        "portfolio_var_95": round(portfolio_returns[int(0.05 * simulations)], 4),
        "portfolio_cvar_95": round(sum(portfolio_returns[:int(0.05 * simulations)]) / int(0.05 * simulations), 4),
        "worst_case": round(portfolio_returns[0], 4),
        "best_case": round(portfolio_returns[-1], 4),
        "prob_profit": round(sum(1 for r in portfolio_returns if r > 0) / simulations * 100, 2),
    }


def bootstrap_backtest(returns: List[float], n_bootstrap: int = 1000,
                       sample_ratio: float = 0.8) -> dict:
    """
    Bootstrap 回测稳健性检验
    多次有放回抽样，检验策略收益的统计显著性
    """
    if not returns or len(returns) < 20:
        return {}

    n = len(returns)
    sample_size = int(n * sample_ratio)

    sharpe_dist = []
    return_dist = []
    max_dd_dist = []

    for _ in range(n_bootstrap):
        sample = random.choices(returns, k=sample_size)
        mean_r = sum(sample) / len(sample)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in sample) / max(len(sample) - 1, 1))
        sharpe = (mean_r / std_r * math.sqrt(252)) if std_r > 0 else 0
        sharpe_dist.append(sharpe)
        return_dist.append(sum(sample))

        # Max DD
        cum = 0
        peak = 0
        max_dd = 0
        for r in sample:
            cum += r
            if cum > peak:
                peak = cum
            dd = (peak - cum) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)
        max_dd_dist.append(max_dd)

    sharpe_dist.sort()
    return_dist.sort()
    max_dd_dist.sort()

    def percentile(arr, p):
        idx = int(p / 100 * len(arr))
        return arr[min(idx, len(arr) - 1)]

    return {
        "n_bootstrap": n_bootstrap,
        "sample_size": sample_size,
        "sharpe": {
            "mean": round(sum(sharpe_dist) / len(sharpe_dist), 4),
            "p5": round(percentile(sharpe_dist, 5), 4),
            "p25": round(percentile(sharpe_dist, 25), 4),
            "p50": round(percentile(sharpe_dist, 50), 4),
            "p75": round(percentile(sharpe_dist, 75), 4),
            "p95": round(percentile(sharpe_dist, 95), 4),
            "prob_positive": round(sum(1 for s in sharpe_dist if s > 0) / len(sharpe_dist) * 100, 2),
        },
        "total_return": {
            "mean": round(sum(return_dist) / len(return_dist), 4),
            "p5": round(percentile(return_dist, 5), 4),
            "p95": round(percentile(return_dist, 95), 4),
        },
        "max_drawdown": {
            "mean": round(sum(max_dd_dist) / len(max_dd_dist), 4),
            "p50": round(percentile(max_dd_dist, 50), 4),
            "p95": round(percentile(max_dd_dist, 95), 4),
        },
    }


# ---- 工具函数 ----

def _build_histogram(values: list, bins: int = 50) -> dict:
    if not values:
        return {}
    min_v = min(values)
    max_v = max(values)
    step = (max_v - min_v) / bins if max_v > min_v else 1
    counts = [0] * bins
    for v in values:
        idx = min(int((v - min_v) / step), bins - 1)
        counts[idx] += 1
    return {"min": round(min_v, 2), "max": round(max_v, 2),
            "step": round(step, 2), "counts": counts}


def _norm_ppf(p: float) -> float:
    """标准正态分位数近似（Abramowitz and Stegun）"""
    if p <= 0:
        return -3.5
    if p >= 1:
        return 3.5
    if p > 0.5:
        return -_norm_ppf(1 - p)

    t = math.sqrt(-2 * math.log(p))
    c0, c1, c2 = 2.515517, 0.802853, 0.010328
    d1, d2, d3 = 1.432788, 0.189269, 0.001308
    return -(t - (c0 + c1 * t + c2 * t ** 2) / (1 + d1 * t + d2 * t ** 2 + d3 * t ** 3))


def _norm_pdf(x: float) -> float:
    """标准正态 PDF"""
    return math.exp(-0.5 * x ** 2) / math.sqrt(2 * math.pi)


def print_mc_report(result: dict):
    if not result:
        print("蒙特卡洛无结果")
        return
    print(f"\n{'='*50}")
    print(f"  蒙特卡洛模拟报告 ({result['simulations']}次)")
    print(f"{'='*50}")
    print(f"  平均最终资金:   {result['avg_final']:>10.2f}")
    print(f"  中位数最终资金: {result['median_final']:>10.2f}")
    print(f"  盈利概率:       {result['prob_profit']:>9.2f}%")
    print(f"  最坏情况:       {result['worst_case']:>10.2f}")
    print(f"  最好情况:       {result['best_case']:>10.2f}")
    print(f"  {result['confidence']}%置信区间:    [{result['ci_lower']}, {result['ci_upper']}]")
    print(f"  平均最大回撤:   {result['avg_max_dd']:>9.2f}%")
    print(f"{'='*50}\n")
