"""
策略注册表
"""
from typing import Optional, Dict, Type, List as TList
from strategy.base import StrategyBase
from strategy.ma_cross import MACrossStrategy
from strategy.rsi import RSIStrategy
from strategy.macd import MACDStrategy
from strategy.bollinger import BollingerStrategy
from strategy.multi_tf import MultiTFStrategy
from strategy.combo import ComboStrategy

_REGISTRY: Dict[str, Type[StrategyBase]] = {
    "ma_cross": MACrossStrategy,
    "rsi": RSIStrategy,
    "macd": MACDStrategy,
    "bollinger": BollingerStrategy,
    "multi_tf": MultiTFStrategy,
    "combo": ComboStrategy,
}


def list_strategies() -> list:
    """列出所有可用策略"""
    return [
        {"name": cls.name, "description": cls.description, "default_params": cls.default_params}
        for cls in _REGISTRY.values()
    ]


def get_strategy(name: str, **params) -> Optional[StrategyBase]:
    """获取策略实例"""
    cls = _REGISTRY.get(name)
    if cls is None:
        return None
    return cls(**params)


def generate_signals(strategy_name: str, candles: list, **params) -> list:
    """用指定策略生成信号"""
    s = get_strategy(strategy_name, **params)
    if s is None:
        return []
    return s.generate_signals(candles)
