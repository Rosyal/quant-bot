"""
风控管理器
"""
from utils.logger import get_logger
from config import (
    RISK_STOP_LOSS, RISK_TAKE_PROFIT, RISK_TRAILING_STOP,
    RISK_MAX_DAILY_TRADES, RISK_MAX_DAILY_LOSS, RISK_MAX_CONSECUTIVE_LOSSES,
)

logger = get_logger("risk.manager")


class RiskManager:
    """风控管理器"""

    def __init__(self, stop_loss: float = RISK_STOP_LOSS,
                 take_profit: float = RISK_TAKE_PROFIT,
                 trailing_stop: float = RISK_TRAILING_STOP,
                 max_daily_trades: int = RISK_MAX_DAILY_TRADES,
                 max_daily_loss: float = RISK_MAX_DAILY_LOSS,
                 max_consecutive_losses: int = RISK_MAX_CONSECUTIVE_LOSSES):
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.trailing_stop = trailing_stop
        self.max_daily_trades = max_daily_trades
        self.max_daily_loss = max_daily_loss
        self.max_consecutive_losses = max_consecutive_losses

        self._daily_trades = 0
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._peak_price = 0.0
        self._current_date = None

    def check_signal(self, signal: str, buy_price: float, current_price: float,
                     position: float, daily_pnl: float = 0.0) -> str:
        """
        检查信号是否通过风控。
        返回: "buy"/"sell"/"hold"（可能覆盖原信号）
        """
        # 每日交易次数限制
        if self.max_daily_trades > 0 and self._daily_trades >= self.max_daily_trades:
            logger.info(f"风控: 达到每日最大交易次数 {self.max_daily_trades}")
            return "hold"

        # 每日亏损限制
        if self.max_daily_loss > 0 and daily_pnl < -self.max_daily_loss:
            logger.info(f"风控: 达到每日最大亏损 {self.max_daily_loss}%")
            return "hold"

        # 连亏暂停
        if self.max_consecutive_losses > 0 and self._consecutive_losses >= self.max_consecutive_losses:
            logger.info(f"风控: 连亏 {self._consecutive_losses} 次，暂停交易")
            return "hold"

        # 持仓风控
        if position > 0 and buy_price > 0:
            pnl_pct = (current_price - buy_price) / buy_price * 100

            # 止损
            if self.stop_loss > 0 and pnl_pct <= -self.stop_loss:
                logger.info(f"风控: 触发止损 (亏损 {pnl_pct:.1f}%)")
                return "sell"

            # 止盈
            if self.take_profit > 0 and pnl_pct >= self.take_profit:
                logger.info(f"风控: 触发止盈 (盈利 {pnl_pct:.1f}%)")
                return "sell"

            # 移动止损
            if self.trailing_stop > 0:
                if current_price > self._peak_price:
                    self._peak_price = current_price
                trail_pct = (self._peak_price - current_price) / self._peak_price * 100
                if trail_pct >= self.trailing_stop:
                    logger.info(f"风控: 触发移动止损 (回撤 {trail_pct:.1f}%)")
                    return "sell"

        return signal

    def record_trade(self, profit: float = 0.0):
        """记录交易结果"""
        self._daily_trades += 1
        self._daily_pnl += profit
        if profit < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

    def reset_daily(self):
        """重置每日统计"""
        self._daily_trades = 0
        self._daily_pnl = 0.0
