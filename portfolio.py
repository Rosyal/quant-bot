"""
投资组合管理 — 风险平价 + 再平衡 + 分析
机构级别：Sharpe/Sortino/Calmar + 相关性矩阵 + 有效前沿
"""
import math
import json
import os
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("portfolio")

PORTFOLIO_DATA_DIR = "data/portfolios"


@dataclass
class AssetPosition:
    """资产持仓"""
    symbol: str = ""
    amount: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    weight: float = 0.0       # 目标权重
    actual_weight: float = 0.0  # 实际权重


@dataclass
class PortfolioConfig:
    """组合配置"""
    name: str = "default"
    rebalance_threshold: float = 5.0   # 偏离阈值 %
    rebalance_interval_days: int = 30  # 再平衡间隔
    max_single_weight: float = 40.0    # 单资产最大权重 %
    min_single_weight: float = 2.0     # 单资产最小权重 %
    risk_free_rate: float = 0.02       # 无风险利率
    lookback_days: int = 252           # 分析回溯天数


class PortfolioManager:
    """投资组合管理器 — 机构级别"""

    def __init__(self, config: PortfolioConfig = None):
        self.config = config or PortfolioConfig()
        self._positions: Dict[str, AssetPosition] = {}
        self._returns_history: Dict[str, List[float]] = {}
        self._last_rebalance: float = 0
        self._portfolio_value: float = 0

    # ---- 持仓管理 ----

    def set_positions(self, positions: List[dict]):
        """设置持仓"""
        self._positions.clear()
        total_value = 0
        for p in positions:
            pos = AssetPosition(
                symbol=p["symbol"],
                amount=p.get("amount", 0),
                entry_price=p.get("entry_price", 0),
                current_price=p.get("current_price", p.get("entry_price", 0)),
                weight=p.get("weight", 0),
            )
            self._positions[pos.symbol] = pos
            total_value += pos.amount * pos.current_price

        self._portfolio_value = total_value
        # 计算实际权重
        for pos in self._positions.values():
            if total_value > 0:
                pos.actual_weight = (pos.amount * pos.current_price / total_value) * 100

    def update_prices(self, prices: Dict[str, float]):
        """更新价格"""
        for symbol, price in prices.items():
            if symbol in self._positions:
                self._positions[symbol].current_price = price

        # 重算实际权重
        total_value = sum(p.amount * p.current_price for p in self._positions.values())
        self._portfolio_value = total_value
        for pos in self._positions.values():
            if total_value > 0:
                pos.actual_weight = (pos.amount * pos.current_price / total_value) * 100

    def add_returns(self, symbol: str, returns: List[float]):
        """添加收益历史"""
        self._returns_history[symbol] = returns

    # ---- 风险平价 ----

    def risk_parity_weights(self) -> Dict[str, float]:
        """
        风险平价权重分配
        每个资产的风险贡献相等
        """
        if not self._returns_history:
            # 无历史数据时等权
            n = len(self._positions)
            if n == 0:
                return {}
            return {s: 100.0 / n for s in self._positions}

        # 计算各资产波动率
        volatilities = {}
        for symbol, returns in self._returns_history.items():
            if len(returns) < 2:
                volatilities[symbol] = 1.0
                continue
            mean = sum(returns) / len(returns)
            var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
            volatilities[symbol] = math.sqrt(var * 252)  # 年化波动率

        # 风险平价：权重 ∝ 1/波动率
        inv_vols = {s: 1.0 / v if v > 0 else 0 for s, v in volatilities.items()}
        total_inv = sum(inv_vols.values())
        if total_inv == 0:
            n = len(volatilities)
            return {s: 100.0 / n for s in volatilities}

        weights = {s: v / total_inv * 100 for s, v in inv_vols.items()}

        # 应用权重约束
        for s in weights:
            weights[s] = max(self.config.min_single_weight,
                             min(self.config.max_single_weight, weights[s]))

        # 重新归一化
        total = sum(weights.values())
        if total > 0:
            weights = {s: w / total * 100 for s, w in weights.items()}

        return weights

    # ---- 再平衡 ----

    def check_rebalance(self) -> List[dict]:
        """检查是否需要再平衡，返回需要调整的订单"""
        orders = []

        # 检查时间间隔
        days_since = (time.time() - self._last_rebalance) / 86400
        if days_since < self.config.rebalance_interval_days:
            # 只检查阈值
            pass

        # 检查权重偏离
        target_weights = self.risk_parity_weights()
        for symbol, pos in self._positions.items():
            target = target_weights.get(symbol, 0)
            actual = pos.actual_weight
            deviation = abs(actual - target)

            if deviation > self.config.rebalance_threshold:
                diff = target - actual
                if self._portfolio_value > 0:
                    trade_value = diff / 100 * self._portfolio_value
                    trade_amount = trade_value / pos.current_price if pos.current_price > 0 else 0
                    orders.append({
                        "symbol": symbol,
                        "action": "buy" if diff > 0 else "sell",
                        "amount": round(abs(trade_amount), 6),
                        "target_weight": round(target, 2),
                        "current_weight": round(actual, 2),
                        "deviation": round(deviation, 2),
                    })

        if orders:
            self._last_rebalance = time.time()

        return orders

    def rebalance(self) -> List[dict]:
        """执行再平衡（check_rebalance 的别名，兼容 API）"""
        return self.check_rebalance()

    # ---- 组合分析 ----

    def portfolio_stats(self) -> dict:
        """组合统计指标 — Sharpe/Sortino/Calmar"""
        if not self._returns_history:
            return {"error": "无收益历史数据"}

        # 计算组合收益
        weights = self.risk_parity_weights()
        all_periods = set()
        for returns in self._returns_history.values():
            all_periods.update(range(len(returns)))

        portfolio_returns = []
        for t in sorted(all_periods):
            ret = 0
            for symbol, returns in self._returns_history.items():
                if t < len(returns):
                    w = weights.get(symbol, 0) / 100
                    ret += w * returns[t]
            portfolio_returns.append(ret)

        if not portfolio_returns:
            return {"error": "无有效收益数据"}

        return self._calc_stats(portfolio_returns)

    def _calc_stats(self, returns: List[float]) -> dict:
        """计算统计指标"""
        n = len(returns)
        if n == 0:
            return {}

        mean_r = sum(returns) / n
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in returns) / max(n - 1, 1))

        # 年化
        annual_return = mean_r * 252
        annual_std = std_r * math.sqrt(252)

        # Sharpe Ratio
        sharpe = (annual_return - self.config.risk_free_rate) / annual_std if annual_std > 0 else 0

        # Sortino Ratio（只考虑下行波动）
        downside = [r for r in returns if r < 0]
        if downside:
            downside_std = math.sqrt(sum(r ** 2 for r in downside) / len(downside)) * math.sqrt(252)
            sortino = (annual_return - self.config.risk_free_rate) / downside_std if downside_std > 0 else 0
        else:
            sortino = float('inf') if annual_return > self.config.risk_free_rate else 0

        # Max Drawdown
        cum = 0
        peak = 0
        max_dd = 0
        for r in returns:
            cum += r
            if cum > peak:
                peak = cum
            dd = (peak - cum) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # Calmar Ratio
        calmar = annual_return / max_dd if max_dd > 0 else float('inf')

        # Win Rate
        wins = sum(1 for r in returns if r > 0)

        # VaR (Historical 95%)
        sorted_r = sorted(returns)
        var_95 = sorted_r[int(0.05 * n)] if n > 20 else 0

        # CVaR
        cvar_idx = int(0.05 * n)
        cvar_95 = sum(sorted_r[:cvar_idx + 1]) / (cvar_idx + 1) if cvar_idx > 0 else sorted_r[0]

        return {
            "total_return": round(sum(returns), 4),
            "annual_return": round(annual_return, 4),
            "annual_volatility": round(annual_std, 4),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4) if sortino != float('inf') else "inf",
            "calmar_ratio": round(calmar, 4) if calmar != float('inf') else "inf",
            "max_drawdown": round(max_dd, 4),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "win_rate": round(wins / n * 100, 2),
            "total_trades": n,
            "var_95": round(var_95, 4),
            "cvar_95": round(cvar_95, 4),
            "avg_return": round(mean_r, 4),
            "best_day": round(max(returns), 4),
            "worst_day": round(min(returns), 4),
        }

    def correlation_matrix(self) -> dict:
        """资产相关性矩阵"""
        if not self._returns_history or len(self._returns_history) < 2:
            return {}

        symbols = list(self._returns_history.keys())
        n = len(symbols)
        matrix = {}

        for i in range(n):
            for j in range(n):
                si, sj = symbols[i], symbols[j]
                ri = self._returns_history[si]
                rj = self._returns_history[sj]
                min_len = min(len(ri), len(rj))
                if min_len < 2:
                    corr = 0
                else:
                    mean_i = sum(ri[:min_len]) / min_len
                    mean_j = sum(rj[:min_len]) / min_len
                    cov = sum((ri[k] - mean_i) * (rj[k] - mean_j) for k in range(min_len)) / (min_len - 1)
                    std_i = math.sqrt(sum((r - mean_i) ** 2 for r in ri[:min_len]) / (min_len - 1))
                    std_j = math.sqrt(sum((r - mean_j) ** 2 for r in rj[:min_len]) / (min_len - 1))
                    corr = cov / (std_i * std_j) if std_i > 0 and std_j > 0 else 0

                matrix[f"{si}:{sj}"] = round(corr, 4)

        return {"symbols": symbols, "matrix": matrix}

    def efficient_frontier(self, n_points: int = 20) -> List[dict]:
        """
        有效前沿（简化版）
        返回不同风险水平下的最优组合权重
        """
        if not self._returns_history or len(self._returns_history) < 2:
            return []

        symbols = list(self._returns_history.keys())
        n = len(symbols)

        # 计算各资产均值和标准差
        stats = {}
        for s in symbols:
            rets = self._returns_history[s]
            mean = sum(rets) / len(rets)
            std = math.sqrt(sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1))
            stats[s] = {"mean": mean, "std": std}

        frontier = []
        # 从最小风险到最大收益
        for i in range(n_points):
            t = i / max(n_points - 1, 1)  # 0 → 1

            # 简化：在等权和最大夏普之间插值
            equal_w = {s: 100.0 / n for s in symbols}
            max_sharpe_w = self.risk_parity_weights()

            weights = {}
            for s in symbols:
                w = equal_w[s] * (1 - t) + max_sharpe_w.get(s, equal_w[s]) * t
                weights[s] = round(w, 2)

            # 计算组合指标
            port_mean = sum(stats[s]["mean"] * weights.get(s, 0) / 100 for s in symbols)
            port_std = sum(stats[s]["std"] * weights.get(s, 0) / 100 for s in symbols)

            frontier.append({
                "weights": weights,
                "expected_return": round(port_mean * 252, 4),
                "expected_volatility": round(port_std * math.sqrt(252), 4),
                "sharpe": round((port_mean * 252 - self.config.risk_free_rate) / (port_std * math.sqrt(252)), 4) if port_std > 0 else 0,
            })

        return frontier

    # ---- 查询 ----

    def get_positions(self) -> List[dict]:
        return [asdict(p) for p in self._positions.values()]

    def get_portfolio_value(self) -> float:
        return self._portfolio_value

    def get_summary(self) -> dict:
        return {
            "name": self.config.name,
            "value": round(self._portfolio_value, 2),
            "positions": len(self._positions),
            "last_rebalance": datetime.fromtimestamp(self._last_rebalance).isoformat() if self._last_rebalance else "",
        }
