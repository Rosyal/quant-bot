"""
参数敏感性分析
"""
from utils.logger import get_logger

logger = get_logger("optimizer.sensitivity")


def sensitivity_analysis(candles: list[dict], strategy_name: str,
                         base_params: dict, vary_param: str,
                         values: list, symbol: str = "BTC/USDT") -> list[dict]:
    """
    单参数敏感性分析：固定其他参数，变化一个参数，观察收益变化。
    """
    from optimizer.grid_search import grid_search

    param_grid = {k: [v] for k, v in base_params.items() if k != vary_param}
    param_grid[vary_param] = values

    results = grid_search(candles, strategy_name, param_grid, symbol)
    return results
