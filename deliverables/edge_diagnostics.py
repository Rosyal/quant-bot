"""
历史回测样本诊断：统计充分性、相对基准、风险指标 — 用于「是否值得继续验证」,
不是预测未来收益或保证赚钱。
"""
from __future__ import annotations

import math
from typing import Any


def diagnose_backtest_sample(result: dict[str, Any]) -> dict[str, Any]:
    """
    返回 flags / tier / robustness_score(0–100 启发式)。
    """
    if not result:
        return {
            "tier": "no_result",
            "flags": ["回测无有效结果"],
            "robustness_score": 0,
            "summary": "无法诊断",
        }

    flags: list[str] = []
    total_trades = int(result.get("total_trades") or 0)
    sells = int(result.get("sell_count") or 0)

    if total_trades < 10:
        flags.append("成交笔数极少，样本几乎无统计意义")
    elif total_trades < 25:
        flags.append("成交笔数偏少，结论需谨慎")
    if sells < 5:
        flags.append("完整平仓轮次过少，胜率和盈亏比不稳定")

    alpha = result.get("alpha_profit_pct")
    if isinstance(alpha, (int, float)) and not math.isnan(float(alpha)):
        if float(alpha) < -5:
            flags.append("相对买入持有显著落后（历史样本）")
        elif float(alpha) < 0:
            flags.append("相对买入持有略落后（历史样本）")

    m = result.get("metrics") or {}
    sharpe = m.get("sharpe")
    if sharpe is not None:
        try:
            s = float(sharpe)
            if s < 0:
                flags.append("夏普率为负（历史样本）")
            elif s < 0.3:
                flags.append("夏普率偏低，风险调整后收益不明显")
        except (TypeError, ValueError):
            pass

    mdd_pct = m.get("max_drawdown_pct")
    if mdd_pct is not None:
        try:
            d = float(mdd_pct)
            if d <= -35.0:
                flags.append("最大回撤较深（历史样本）")
        except (TypeError, ValueError):
            pass

    pf = result.get("profit_factor")
    if pf is not None and isinstance(pf, (int, float)) and math.isfinite(float(pf)):
        if float(pf) < 0.8:
            flags.append("盈亏比偏弱（profit factor，历史样本）")

    tier, summary = _tier_from_flags(flags, result)
    score = _robustness_score(result, flags)

    return {
        "tier": tier,
        "flags": flags or ["未触发明显红线（仍需样本外检验）"],
        "robustness_score": score,
        "summary": summary,
    }


def _tier_from_flags(flags: list[str], result: dict[str, Any]) -> tuple[str, str]:
    if any("无统计意义" in f or "极少" in f for f in flags):
        return "insufficient_data", "历史样本过短，仅适合探索，不适合对外承诺表现"
    if any("显著落后" in f for f in flags) and any("夏普率为负" in f for f in flags):
        return "weak_sample", "历史样本风险收益较差，不建议作为卖点宣传"
    sh = (result.get("metrics") or {}).get("sharpe")
    if len(flags) <= 1 and sh is not None and float(sh) > 0.8:
        return "needs_oos", "历史样本尚可，但必须配合 walk-forward / 纸面验证后才能对外表述"
    return "neutral", "中性：需更多数据与样本外检验后再评估"


def _robustness_score(result: dict[str, Any], flags: list[str]) -> int:
    score = 55
    n = int(result.get("total_trades") or 0)
    if n >= 40:
        score += 15
    elif n >= 20:
        score += 8
    else:
        score -= 18

    alpha = result.get("alpha_profit_pct")
    if isinstance(alpha, (int, float)) and not math.isnan(float(alpha)):
        if float(alpha) > 2:
            score += 12
        elif float(alpha) > 0:
            score += 5
        else:
            score -= 12

    sharpe = (result.get("metrics") or {}).get("sharpe")
    if sharpe is not None:
        try:
            s = float(sharpe)
            if s > 1.0:
                score += 10
            elif s > 0.5:
                score += 4
            elif s < 0:
                score -= 14
        except (TypeError, ValueError):
            pass

    score -= min(20, len(flags) * 4)
    return max(0, min(100, score))
