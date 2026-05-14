"""
A股因子选股库 — 聚宽/米筐 级别
12+因子 + IC/IR 分析 + 行业中性 + 多因子打分 + 因子回测
"""
import math
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

from utils.logger import get_logger

logger = get_logger("factor_library")

FACTOR_DATA_DIR = "data/factors"


# ============================================================
# 因子定义
# ============================================================

class FactorCategory:
    VALUE = "value"           # 价值
    GROWTH = "growth"         # 成长
    QUALITY = "quality"       # 质量
    MOMENTUM = "momentum"     # 动量
    VOLATILITY = "volatility" # 波动
    LIQUIDITY = "liquidity"   # 流动性
    TECHNICAL = "technical"   # 技术
    SENTIMENT = "sentiment"   # 情绪


@dataclass
class FactorDef:
    """因子定义"""
    name: str = ""
    display_name: str = ""
    category: str = ""
    direction: int = 1       # 1=越大越好, -1=越小越好
    description: str = ""
    weight: float = 1.0      # 默认权重


# 标准因子库
BUILTIN_FACTORS = {
    # ---- 价值因子 ----
    "pe_ratio": FactorDef("pe_ratio", "PE(TTM)", FactorCategory.VALUE, -1, "市盈率，越低越便宜"),
    "pb_ratio": FactorDef("pb_ratio", "PB", FactorCategory.VALUE, -1, "市净率，越低越便宜"),
    "ps_ratio": FactorDef("ps_ratio", "PS", FactorCategory.VALUE, -1, "市销率，越低越便宜"),
    "pcf_ratio": FactorDef("pcf_ratio", "PCF", FactorCategory.VALUE, -1, "市现率，越低越便宜"),
    "ev_ebitda": FactorDef("ev_ebitda", "EV/EBITDA", FactorCategory.VALUE, -1, "企业价值/EBITDA"),
    "dividend_yield": FactorDef("dividend_yield", "股息率", FactorCategory.VALUE, 1, "股息率，越高越好"),
    # ---- 成长因子 ----
    "revenue_growth": FactorDef("revenue_growth", "营收增速", FactorCategory.GROWTH, 1, "营收同比增长率"),
    "profit_growth": FactorDef("profit_growth", "利润增速", FactorCategory.GROWTH, 1, "净利润同比增长率"),
    "eps_growth": FactorDef("eps_growth", "EPS增速", FactorCategory.GROWTH, 1, "每股收益增速"),
    "roe_growth": FactorDef("roe_growth", "ROE变化", FactorCategory.GROWTH, 1, "ROE同比变化"),
    "operating_leverage": FactorDef("operating_leverage", "经营杠杆", FactorCategory.GROWTH, 1, "经营杠杆系数"),
    # ---- 质量因子 ----
    "roe": FactorDef("roe", "ROE", FactorCategory.QUALITY, 1, "净资产收益率"),
    "roa": FactorDef("roa", "ROA", FactorCategory.QUALITY, 1, "总资产收益率"),
    "gross_margin": FactorDef("gross_margin", "毛利率", FactorCategory.QUALITY, 1, "毛利率"),
    "net_margin": FactorDef("net_margin", "净利率", FactorCategory.QUALITY, 1, "净利率"),
    "current_ratio": FactorDef("current_ratio", "流动比率", FactorCategory.QUALITY, 1, "流动比率"),
    "debt_to_equity": FactorDef("debt_to_equity", "资产负债率", FactorCategory.QUALITY, -1, "资产负债率"),
    "accruals": FactorDef("accruals", "应计利润", FactorCategory.QUALITY, -1, "应计项目质量"),
    # ---- 动量因子 ----
    "momentum_1m": FactorDef("momentum_1m", "1月动量", FactorCategory.MOMENTUM, 1, "近1月收益率"),
    "momentum_3m": FactorDef("momentum_3m", "3月动量", FactorCategory.MOMENTUM, 1, "近3月收益率"),
    "momentum_6m": FactorDef("momentum_6m", "6月动量", FactorCategory.MOMENTUM, 1, "近6月收益率"),
    "momentum_12m": FactorDef("momentum_12m", "12月动量", FactorCategory.MOMENTUM, 1, "近12月收益率"),
    "reversal_5d": FactorDef("reversal_5d", "5日反转", FactorCategory.MOMENTUM, -1, "短期反转因子"),
    # ---- 波动因子 ----
    "volatility_20d": FactorDef("volatility_20d", "20日波动率", FactorCategory.VOLATILITY, -1, "20日年化波动率"),
    "volatility_60d": FactorDef("volatility_60d", "60日波动率", FactorCategory.VOLATILITY, -1, "60日年化波动率"),
    "beta": FactorDef("beta", "Beta", FactorCategory.VOLATILITY, -1, "相对沪深300的Beta"),
    "idio_vol": FactorDef("idio_vol", "特质波动率", FactorCategory.VOLATILITY, -1, "残差波动率"),
    # ---- 流动性因子 ----
    "turnover_20d": FactorDef("turnover_20d", "20日换手率", FactorCategory.LIQUIDITY, -1, "20日平均换手率"),
    "amihud_illiq": FactorDef("amihud_illiq", "Amihud非流动性", FactorCategory.LIQUIDITY, -1, "Amihud非流动性指标"),
    "volume_ratio": FactorDef("volume_ratio", "量比", FactorCategory.LIQUIDITY, 1, "当日量比"),
    # ---- 技术因子 ----
    "rsi_14": FactorDef("rsi_14", "RSI(14)", FactorCategory.TECHNICAL, 1, "14日RSI"),
    "macd_signal": FactorDef("macd_signal", "MACD信号", FactorCategory.TECHNICAL, 1, "MACD金叉/死叉"),
    "bollinger_pos": FactorDef("bollinger_pos", "布林位置", FactorCategory.TECHNICAL, 1, "布林带位置(0-100)"),
    "ma5_ma20": FactorDef("ma5_ma20", "MA5/MA20", FactorCategory.TECHNICAL, 1, "5日/20日均线交叉"),
    # ---- 情绪因子 ----
    "analyst_rating": FactorDef("analyst_rating", "分析师评级", FactorCategory.SENTIMENT, 1, "分析师平均评级"),
    "institution_holding": FactorDef("institution_holding", "机构持仓", FactorCategory.SENTIMENT, 1, "机构持仓比例变化"),
}


# ============================================================
# 因子计算
# ============================================================

class FactorCalculator:
    """因子计算器"""

    @staticmethod
    def calc_pe_ratio(price: float, eps_ttm: float) -> float:
        return price / eps_ttm if eps_ttm and eps_ttm > 0 else float("inf")

    @staticmethod
    def calc_pb_ratio(price: float, bvps: float) -> float:
        return price / bvps if bvps and bvps > 0 else float("inf")

    @staticmethod
    def calc_roe(net_income: float, equity: float) -> float:
        return net_income / equity if equity and equity != 0 else 0

    @staticmethod
    def calc_roa(net_income: float, total_assets: float) -> float:
        return net_income / total_assets if total_assets and total_assets != 0 else 0

    @staticmethod
    def calc_gross_margin(revenue: float, cost: float) -> float:
        return (revenue - cost) / revenue if revenue and revenue != 0 else 0

    @staticmethod
    def calc_net_margin(net_income: float, revenue: float) -> float:
        return net_income / revenue if revenue and revenue != 0 else 0

    @staticmethod
    def calc_momentum(current_price: float, past_price: float) -> float:
        return (current_price - past_price) / past_price if past_price and past_price != 0 else 0

    @staticmethod
    def calc_volatility(returns: List[float]) -> float:
        if len(returns) < 2:
            return 0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        return math.sqrt(var) * math.sqrt(252)  # 年化

    @staticmethod
    def calc_beta(stock_returns: List[float], market_returns: List[float]) -> float:
        if len(stock_returns) < 2 or len(market_returns) < 2:
            return 1.0
        n = min(len(stock_returns), len(market_returns))
        sr = stock_returns[:n]
        mr = market_returns[:n]
        mean_sr = sum(sr) / n
        mean_mr = sum(mr) / n
        cov = sum((sr[i] - mean_sr) * (mr[i] - mean_mr) for i in range(n)) / (n - 1)
        var_m = sum((mr[i] - mean_mr) ** 2 for i in range(n)) / (n - 1)
        return cov / var_m if var_m > 0 else 1.0

    @staticmethod
    def calc_rsi(prices: List[float], period: int = 14) -> float:
        if len(prices) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            gains.append(max(change, 0))
            losses.append(max(-change, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calc_amihud(daily_returns: List[float], daily_volumes: List[float]) -> float:
        """Amihud 非流动性指标"""
        if not daily_returns or not daily_volumes:
            return 0
        n = min(len(daily_returns), len(daily_volumes))
        ratios = []
        for i in range(n):
            if daily_volumes[i] > 0 and daily_returns[i] != 0:
                ratios.append(abs(daily_returns[i]) / daily_volumes[i])
        return sum(ratios) / len(ratios) if ratios else 0

    @staticmethod
    def calc_accruals(net_income: float, operating_cash_flow: float, total_assets: float) -> float:
        """应计利润 = (净利润 - 经营现金流) / 总资产"""
        if total_assets == 0:
            return 0
        return (net_income - operating_cash_flow) / total_assets


# ============================================================
# IC/IR 分析 — 因子有效性检验
# ============================================================

@dataclass
class ICResult:
    """IC 分析结果"""
    factor_name: str = ""
    ic_mean: float = 0.0       # IC 均值
    ic_std: float = 0.0        # IC 标准差
    ir: float = 0.0            # 信息比率 = IC均值/IC标准差
    ic_positive_rate: float = 0.0  # IC>0 的比例
    t_stat: float = 0.0        # t 统计量
    p_value: float = 0.0       # p 值
    period_count: int = 0      # 期数
    is_effective: bool = False  # 是否有效


class ICAnalyzer:
    """IC/IR 分析器 — 因子有效性检验核心"""

    def __init__(self, min_periods: int = 12, ic_threshold: float = 0.03,
                 ir_threshold: float = 0.5, significance: float = 0.05):
        self.min_periods = min_periods
        self.ic_threshold = ic_threshold
        self.ir_threshold = ir_threshold
        self.significance = significance

    def calc_rank_ic(self, factor_values: Dict[str, float],
                     forward_returns: Dict[str, float]) -> float:
        """计算 Rank IC（Spearman 相关系数）"""
        common = set(factor_values.keys()) & set(forward_returns.keys())
        if len(common) < 5:
            return 0.0

        pairs = [(factor_values[k], forward_returns[k]) for k in common]
        factor_rank = self._rank([p[0] for p in pairs])
        return_rank = self._rank([p[1] for p in pairs])

        n = len(factor_rank)
        mean_f = sum(factor_rank) / n
        mean_r = sum(return_rank) / n

        cov = sum((factor_rank[i] - mean_f) * (return_rank[i] - mean_r) for i in range(n)) / n
        std_f = math.sqrt(sum((factor_rank[i] - mean_f) ** 2 for i in range(n)) / n)
        std_r = math.sqrt(sum((return_rank[i] - mean_r) ** 2 for i in range(n)) / n)

        if std_f == 0 or std_r == 0:
            return 0.0
        return cov / (std_f * std_r)

    def analyze_factor(self, factor_name: str,
                       period_factor_values: List[Dict[str, float]],
                       period_forward_returns: List[Dict[str, float]]) -> ICResult:
        """分析单个因子的 IC/IR"""
        if len(period_factor_values) < self.min_periods:
            return ICResult(factor_name=factor_name, period_count=len(period_factor_values))

        ics = []
        for i in range(len(period_factor_values)):
            ic = self.calc_rank_ic(period_factor_values[i], period_forward_returns[i])
            ics.append(ic)

        return self._compute_ic_result(factor_name, ics)

    def analyze_all(self, factor_names: List[str],
                    period_factor_values: Dict[str, List[Dict[str, float]]],
                    period_forward_returns: List[Dict[str, float]]) -> Dict[str, ICResult]:
        """批量分析所有因子"""
        results = {}
        for name in factor_names:
            if name in period_factor_values:
                results[name] = self.analyze_factor(
                    name, period_factor_values[name], period_forward_returns
                )
        return results

    def _compute_ic_result(self, factor_name: str, ics: List[float]) -> ICResult:
        n = len(ics)
        ic_mean = sum(ics) / n
        ic_std = math.sqrt(sum((ic - ic_mean) ** 2 for ic in ics) / (n - 1)) if n > 1 else 0
        ir = ic_mean / ic_std if ic_std > 0 else 0
        ic_positive = sum(1 for ic in ics if ic > 0) / n
        t_stat = ic_mean / (ic_std / math.sqrt(n)) if ic_std > 0 and n > 0 else 0

        # 简化 p 值估计（正态近似）
        p_value = 2 * (1 - self._norm_cdf(abs(t_stat))) if t_stat != 0 else 1.0

        is_effective = (
            abs(ic_mean) >= self.ic_threshold
            and abs(ir) >= self.ir_threshold
            and p_value <= self.significance
        )

        return ICResult(
            factor_name=factor_name, ic_mean=round(ic_mean, 4),
            ic_std=round(ic_std, 4), ir=round(ir, 4),
            ic_positive_rate=round(ic_positive, 4),
            t_stat=round(t_stat, 4), p_value=round(p_value, 4),
            period_count=n, is_effective=is_effective,
        )

    @staticmethod
    def _rank(values: List[float]) -> List[float]:
        """计算排名"""
        indexed = sorted(enumerate(values), key=lambda x: x[1])
        ranks = [0.0] * len(values)
        for rank, (idx, _) in enumerate(indexed, 1):
            ranks[idx] = float(rank)
        return ranks

    @staticmethod
    def _norm_cdf(x: float) -> float:
        """标准正态 CDF 近似"""
        return 0.5 * (1 + math.erf(x / math.sqrt(2)))


# ============================================================
# 行业中性化
# ============================================================

class IndustryNeutralizer:
    """行业中性化处理 — 消除行业偏差"""

    def __init__(self):
        # 申万一级行业分类
        self._industry_map: Dict[str, str] = {}

    def set_industry(self, stock_code: str, industry: str):
        self._industry_map[stock_code] = industry

    def load_industry_data(self, data: Dict[str, str]):
        """批量加载行业数据 {stock_code: industry}"""
        self._industry_map.update(data)

    def neutralize(self, factor_values: Dict[str, float]) -> Dict[str, float]:
        """行业中性化：减去行业均值"""
        if not self._industry_map:
            return factor_values

        # 按行业分组
        industry_groups: Dict[str, List[Tuple[str, float]]] = {}
        for code, value in factor_values.items():
            industry = self._industry_map.get(code, "unknown")
            if industry not in industry_groups:
                industry_groups[industry] = []
            industry_groups[industry].append((code, value))

        # 减去行业均值
        result = {}
        for industry, members in industry_groups.items():
            mean_val = sum(v for _, v in members) / len(members)
            for code, value in members:
                result[code] = value - mean_val

        return result

    def neutralize_zscore(self, factor_values: Dict[str, float]) -> Dict[str, float]:
        """行业中性化 + Z-Score 标准化"""
        if not self._industry_map:
            # 无行业数据时做全局 Z-Score
            return self._zscore(factor_values)

        industry_groups: Dict[str, List[Tuple[str, float]]] = {}
        for code, value in factor_values.items():
            industry = self._industry_map.get(code, "unknown")
            if industry not in industry_groups:
                industry_groups[industry] = []
            industry_groups[industry].append((code, value))

        result = {}
        for industry, members in industry_groups.items():
            values = [v for _, v in members]
            mean_val = sum(values) / len(values)
            std_val = math.sqrt(sum((v - mean_val) ** 2 for v in values) / max(len(values) - 1, 1))
            for code, value in members:
                result[code] = (value - mean_val) / std_val if std_val > 0 else 0

        return result

    @staticmethod
    def _zscore(values: Dict[str, float]) -> Dict[str, float]:
        vals = list(values.values())
        mean = sum(vals) / len(vals)
        std = math.sqrt(sum((v - mean) ** 2 for v in vals) / max(len(vals) - 1, 1))
        return {k: (v - mean) / std if std > 0 else 0 for k, v in values.items()}


# ============================================================
# 多因子打分模型
# ============================================================

@dataclass
class ScoringModel:
    """多因子打分模型配置"""
    name: str = "default"
    factor_weights: Dict[str, float] = field(default_factory=dict)
    neutralize: bool = True       # 是否行业中性化
    zscore: bool = True           # 是否标准化
    top_n: int = 50               # 选股数量
    rebalance_days: int = 5       # 调仓周期（交易日）


class MultiFactorScorer:
    """多因子打分器"""

    def __init__(self, model: ScoringModel = None,
                 neutralizer: IndustryNeutralizer = None):
        self.model = model or ScoringModel()
        self.neutralizer = neutralizer or IndustryNeutralizer()
        self._ic_analyzer = ICAnalyzer()

    def score(self, factor_data: Dict[str, Dict[str, float]]) -> List[Dict]:
        """
        多因子打分
        factor_data: {factor_name: {stock_code: value}}
        返回: [{code, score, rank, factor_scores}]
        """
        weights = self.model.factor_weights
        if not weights:
            # 等权
            weights = {k: 1.0 for k in factor_data}

        # 1. 标准化每个因子
        normalized = {}
        for factor_name, values in factor_data.items():
            if factor_name not in weights:
                continue
            # 行业中性化
            if self.model.neutralize:
                values = self.neutralizer.neutralize_zscore(values) if self.model.zscore else self.neutralizer.neutralize(values)
            elif self.model.zscore:
                values = IndustryNeutralizer._zscore(values)
            normalized[factor_name] = values

        # 2. 加权打分
        all_stocks = set()
        for values in normalized.values():
            all_stocks.update(values.keys())

        total_weight = sum(abs(w) for w in weights.values())
        scores = []
        for code in all_stocks:
            factor_scores = {}
            weighted_sum = 0
            for factor_name, weight in weights.items():
                if factor_name in normalized and code in normalized[factor_name]:
                    # 考虑因子方向
                    direction = BUILTIN_FACTORS.get(factor_name, FactorDef()).direction
                    val = normalized[factor_name][code] * direction
                    factor_scores[factor_name] = round(val, 4)
                    weighted_sum += val * abs(weight)

            final_score = weighted_sum / total_weight if total_weight > 0 else 0
            scores.append({
                "code": code,
                "score": round(final_score, 4),
                "factor_scores": factor_scores,
            })

        # 3. 排名
        scores.sort(key=lambda x: x["score"], reverse=True)
        for i, s in enumerate(scores, 1):
            s["rank"] = i

        return scores

    def select_top(self, factor_data: Dict[str, Dict[str, float]],
                   top_n: int = 0) -> List[Dict]:
        """选股：返回 top N"""
        top_n = top_n or self.model.top_n
        scores = self.score(factor_data)
        return scores[:top_n]


# ============================================================
# 因子回测
# ============================================================

@dataclass
class FactorBacktestResult:
    """因子回测结果"""
    factor_name: str = ""
    total_return: float = 0.0
    annual_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    ic_mean: float = 0.0
    ir: float = 0.0
    period_count: int = 0
    long_returns: List[float] = field(default_factory=list)
    short_returns: List[float] = field(default_factory=list)


class FactorBacktester:
    """因子回测器 — 分层回测法"""

    def __init__(self, n_groups: int = 5, rebalance_days: int = 20):
        self.n_groups = n_groups
        self.rebalance_days = rebalance_days

    def backtest_factor(self, factor_name: str,
                        period_factor_values: List[Dict[str, float]],
                        period_forward_returns: List[Dict[str, float]]) -> FactorBacktestResult:
        """单因子分层回测"""
        if len(period_factor_values) < 3:
            return FactorBacktestResult(factor_name=factor_name)

        long_returns = []  # 顶部组收益
        short_returns = []  # 底部组收益

        for i in range(len(period_factor_values)):
            fvals = period_factor_values[i]
            frets = period_forward_returns[i]

            common = set(fvals.keys()) & set(frets.keys())
            if len(common) < self.n_groups * 2:
                continue

            # 按因子值排序分组
            sorted_stocks = sorted(common, key=lambda k: fvals[k])
            group_size = len(sorted_stocks) // self.n_groups

            # 顶部组（因子值最高）
            top_group = sorted_stocks[-group_size:]
            top_return = sum(frets[s] for s in top_group) / len(top_group)
            long_returns.append(top_return)

            # 底部组（因子值最低）
            bottom_group = sorted_stocks[:group_size]
            bottom_return = sum(frets[s] for s in bottom_group) / len(bottom_group)
            short_returns.append(bottom_return)

        if not long_returns:
            return FactorBacktestResult(factor_name=factor_name)

        # 计算统计指标
        total_return = sum(long_returns)
        annual_return = total_return * (252 / max(self.rebalance_days * len(long_returns), 1))
        mean_ret = sum(long_returns) / len(long_returns)
        std_ret = math.sqrt(sum((r - mean_ret) ** 2 for r in long_returns) / max(len(long_returns) - 1, 1))
        sharpe = (mean_ret / std_ret) * math.sqrt(252 / self.rebalance_days) if std_ret > 0 else 0

        # 最大回撤
        cum_returns = []
        cum = 0
        for r in long_returns:
            cum += r
            cum_returns.append(cum)
        max_dd = 0
        peak = 0
        for cr in cum_returns:
            if cr > peak:
                peak = cr
            dd = (peak - cr) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        # IC 分析
        ic_analyzer = ICAnalyzer()
        ic_result = ic_analyzer.analyze_factor(factor_name, period_factor_values, period_forward_returns)

        return FactorBacktestResult(
            factor_name=factor_name,
            total_return=round(total_return, 4),
            annual_return=round(annual_return, 4),
            sharpe_ratio=round(sharpe, 4),
            max_drawdown=round(max_dd, 4),
            win_rate=round(sum(1 for r in long_returns if r > 0) / len(long_returns), 4),
            ic_mean=ic_result.ic_mean,
            ir=ic_result.ir,
            period_count=len(long_returns),
            long_returns=long_returns,
            short_returns=short_returns,
        )


# ============================================================
# 因子库主类
# ============================================================

class FactorLibrary:
    """因子库 — 聚宽级别"""

    def __init__(self):
        self.calculator = FactorCalculator()
        self.ic_analyzer = ICAnalyzer()
        self.neutralizer = IndustryNeutralizer()
        self.scorer = MultiFactorScorer(neutralizer=self.neutralizer)
        self.backtester = FactorBacktester()
        self._custom_factors: Dict[str, FactorDef] = {}

    def list_factors(self, category: str = "") -> List[dict]:
        """列出所有因子"""
        all_factors = {**BUILTIN_FACTORS, **self._custom_factors}
        result = []
        for name, fdef in all_factors.items():
            if category and fdef.category != category:
                continue
            result.append({
                "name": name,
                "display_name": fdef.display_name,
                "category": fdef.category,
                "direction": fdef.direction,
                "description": fdef.description,
            })
        return result

    def add_factor(self, name: str, display_name: str, category: str,
                   direction: int = 1, description: str = "") -> FactorDef:
        """添加自定义因子"""
        fdef = FactorDef(name=name, display_name=display_name,
                         category=category, direction=direction,
                         description=description)
        self._custom_factors[name] = fdef
        return fdef

    def score_stocks(self, factor_data: Dict[str, Dict[str, float]],
                     model: ScoringModel = None) -> List[Dict]:
        """多因子打分选股"""
        if model:
            self.scorer.model = model
        return self.scorer.score(factor_data)

    def select_stocks(self, factor_data: Dict[str, Dict[str, float]],
                      top_n: int = 50, model: ScoringModel = None) -> List[Dict]:
        """选股"""
        if model:
            self.scorer.model = model
        return self.scorer.select_top(factor_data, top_n)

    def analyze_ic(self, factor_name: str,
                   period_factor_values: List[Dict[str, float]],
                   period_forward_returns: List[Dict[str, float]]) -> ICResult:
        """IC/IR 分析"""
        return self.ic_analyzer.analyze_factor(factor_name, period_factor_values, period_forward_returns)

    def backtest_factor(self, factor_name: str,
                        period_factor_values: List[Dict[str, float]],
                        period_forward_returns: List[Dict[str, float]]) -> FactorBacktestResult:
        """因子回测"""
        return self.backtester.backtest_factor(factor_name, period_factor_values, period_forward_returns)

    def get_categories(self) -> List[dict]:
        """获取因子分类"""
        cats = {}
        for fdef in BUILTIN_FACTORS.values():
            if fdef.category not in cats:
                cats[fdef.category] = 0
            cats[fdef.category] += 1
        return [{"category": k, "count": v} for k, v in cats.items()]

    # ---- 兼容旧 API 的方法 ----

    def screen_top(self, factor_data: Dict[str, Dict[str, float]],
                   top_n: int = 50) -> List[Dict]:
        """筛选 Top N（兼容旧 API）"""
        return self.select_stocks(factor_data, top_n)

    def get_factor_info(self, factor_name: str) -> dict:
        """获取因子信息"""
        all_factors = {**BUILTIN_FACTORS, **self._custom_factors}
        fdef = all_factors.get(factor_name)
        if not fdef:
            return {}
        return {
            "name": fdef.name,
            "display_name": fdef.display_name,
            "category": fdef.category,
            "direction": fdef.direction,
            "description": fdef.description,
        }

    def fetch_a_share_data(self, limit: int = 50) -> List[dict]:
        """获取 A 股因子数据（从 AkShare 实时拉取 + 计算因子）"""
        try:
            from akshare_cache import AkShareCache
            cache = AkShareCache()
            df = cache.get_stock_realtime()
            if df is None or df.empty:
                logger.warning("AkShare 实时行情为空")
                return []

            # 标准化列名（AkShare 东方财富实时行情字段）
            col_map = {
                "代码": "code", "名称": "name",
                "最新价": "price", "涨跌幅": "change_pct",
                "市盈率-动态": "pe_ratio", "市净率": "pb_ratio",
                "总市值": "market_cap", "流通市值": "float_cap",
                "成交量": "volume", "成交额": "amount",
                "换手率": "turnover", "60日涨跌幅": "momentum_60d",
                "年初至今涨跌幅": "ytd_return",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

            # 过滤 ST、退市、停牌
            if "name" in df.columns:
                df = df[~df["name"].str.contains("ST|退|停", na=False)]

            # 过滤无效 PE/PB
            if "pe_ratio" in df.columns:
                df = df[df["pe_ratio"] > 0]
            if "pb_ratio" in df.columns:
                df = df[df["pb_ratio"] > 0]

            # 按市值排序取前 N
            if "market_cap" in df.columns:
                df = df.sort_values("market_cap", ascending=False)

            records = df.head(limit).to_dict("records")

            # 清理 NaN
            import pandas as pd
            for rec in records:
                for k, v in rec.items():
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        rec[k] = None

            return records

        except ImportError:
            logger.warning("akshare 未安装，A股数据不可用")
            return []
        except Exception as e:
            logger.error(f"获取 A 股数据失败: {e}")
            return []

    def fetch_and_score(self, limit: int = 100, top_n: int = 20,
                        factor_names: List[str] = None) -> dict:
        """一键选股：拉数据 → 算因子 → 打分 → 选股"""
        # 1. 拉取实时行情
        stocks = self.fetch_a_share_data(limit)
        if not stocks:
            return {"stocks": [], "scores": [], "error": "无数据"}

        # 2. 构建因子数据矩阵
        if factor_names is None:
            factor_names = ["pe_ratio", "pb_ratio", "change_pct", "turnover"]
            # 只保留数据中实际存在的因子
            available = set()
            for s in stocks:
                available.update(k for k, v in s.items() if v is not None and isinstance(v, (int, float)))
            factor_names = [f for f in factor_names if f in available]

        factor_data: Dict[str, Dict[str, float]] = {}
        for fname in factor_names:
            values = {}
            for s in stocks:
                code = s.get("code", "")
                val = s.get(fname)
                if code and val is not None and isinstance(val, (int, float)):
                    values[code] = float(val)
            if len(values) >= 5:
                factor_data[fname] = values

        if not factor_data:
            return {"stocks": stocks[:top_n], "scores": [], "factor_data": {}}

        # 3. 多因子打分
        scores = self.select_stocks(factor_data, top_n)

        # 4. 补充股票名称
        code_to_name = {s.get("code", ""): s.get("name", "") for s in stocks}
        for s in scores:
            s["name"] = code_to_name.get(s["code"], "")

        return {
            "stocks": stocks[:limit],
            "scores": scores,
            "factor_data": {k: len(v) for k, v in factor_data.items()},
            "total_analyzed": len(stocks),
        }
