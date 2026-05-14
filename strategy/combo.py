"""
组合策略 — 多策略投票/加权
"""
from strategy.base import StrategyBase


class ComboStrategy(StrategyBase):
    name = "combo"
    description = "组合策略（多策略投票制）"
    default_params = {
        "strategies": ["ma_cross", "rsi", "macd"],
        "weights": [1, 1, 1],
        "threshold": 0.5,
    }
    param_space = {
        "threshold": [0.3, 0.5, 0.7],
    }

    def on_candle(self, idx: int, candles: list[dict], extra_timeframes=None) -> str:
        # 延迟导入避免循环依赖
        def _gen_signals(strategy_name, candle_data):
            from strategy import get_strategy
            s = get_strategy(strategy_name)
            if s is None:
                return "hold"
            return s.on_candle(idx, candle_data)

        strategies = self.get_param("strategies", ["ma_cross", "rsi", "macd"])
        weights = self.get_param("weights", [1] * len(strategies))
        threshold = self.get_param("threshold", 0.5)

        if len(weights) < len(strategies):
            weights = weights + [1] * (len(strategies) - len(weights))

        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0

        for sname, w in zip(strategies, weights):
            sig = _gen_signals(sname, candles)
            if sig == "buy":
                buy_score += w
            elif sig == "sell":
                sell_score += w
            total_weight += w

        if total_weight == 0:
            return "hold"

        if buy_score / total_weight >= threshold:
            return "buy"
        if sell_score / total_weight >= threshold:
            return "sell"
        return "hold"
