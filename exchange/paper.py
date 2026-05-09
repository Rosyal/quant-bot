"""
模拟盘交易所
零成本模拟交易，不连接真实交易所
"""
from __future__ import annotations
from datetime import datetime
from utils.logger import get_logger
from config import INITIAL_BALANCE, FEE_RATE, SLIPPAGE_BPS

logger = get_logger("exchange")


class PaperExchange:
    """模拟盘交易所"""

    def __init__(
        self,
        initial_balance: float = INITIAL_BALANCE,
        *,
        fee_rate: float | None = None,
        slippage_bps: float | None = None,
    ):
        self.usdt_balance = initial_balance
        self.coin_balance = 0.0
        self.coin_symbol = ""
        self.fee_rate = FEE_RATE if fee_rate is None else fee_rate
        self.slippage_bps = float(SLIPPAGE_BPS if slippage_bps is None else slippage_bps)
        self.trades: list[dict] = []
        self.initial_balance = initial_balance
        logger.info(f"模拟盘已初始化, 初始资金: {initial_balance} USDT")

    def _exec_buy_price(self, reference_price: float) -> float:
        return reference_price * (1.0 + self.slippage_bps / 10000.0)

    def _exec_sell_price(self, reference_price: float) -> float:
        return max(reference_price * (1.0 - self.slippage_bps / 10000.0), 1e-12)

    def buy(self, symbol: str, price: float, amount_usdt: float) -> dict | None:
        """
        买入
        :param symbol: 交易对
        :param price: 当前价格
        :param amount_usdt: 花多少 USDT 买
        :return: 交易记录
        """
        if amount_usdt > self.usdt_balance:
            logger.warning(f"USDT 不足: 需要 {amount_usdt:.2f}, 可用 {self.usdt_balance:.2f}")
            return None

        exec_px = self._exec_buy_price(price)
        fee = amount_usdt * self.fee_rate
        actual_spend = amount_usdt - fee
        coin_amount = actual_spend / exec_px

        self.usdt_balance -= amount_usdt
        self.coin_balance += coin_amount
        self.coin_symbol = symbol.split("/")[0]

        trade = {
            "symbol": symbol,
            "side": "buy",
            "price": exec_px,
            "amount": coin_amount,
            "fee": fee,
            "total": amount_usdt,
            "timestamp": int(datetime.now().timestamp()),
            "strategy": "",
        }
        self.trades.append(trade)
        logger.info(
            f"买入: {coin_amount:.6f} {self.coin_symbol} "
            f"@ {exec_px:.2f} USDT (手续费: {fee:.4f})"
        )
        return trade

    def sell(self, symbol: str, price: float) -> dict | None:
        """
        卖出全部持仓
        :param symbol: 交易对
        :param price: 当前价格
        :return: 交易记录
        """
        if self.coin_balance <= 0:
            logger.warning("无持仓可卖")
            return None

        coin_amount = self.coin_balance
        exec_px = self._exec_sell_price(price)
        total_usdt = coin_amount * exec_px
        fee = total_usdt * self.fee_rate
        actual_receive = total_usdt - fee

        self.coin_balance = 0
        self.usdt_balance += actual_receive

        trade = {
            "symbol": symbol,
            "side": "sell",
            "price": exec_px,
            "amount": coin_amount,
            "fee": fee,
            "total": actual_receive,
            "timestamp": int(datetime.now().timestamp()),
            "strategy": "",
        }
        self.trades.append(trade)
        logger.info(
            f"卖出: {coin_amount:.6f} {self.coin_symbol} "
            f"@ {exec_px:.2f} USDT (手续费: {fee:.4f})"
        )
        return trade

    def get_balance(self, current_price: float = 0) -> dict:
        """获取当前账户状态"""
        coin_value = self.coin_balance * current_price
        total_value = self.usdt_balance + coin_value
        profit = total_value - self.initial_balance
        profit_pct = (profit / self.initial_balance) * 100 if self.initial_balance else 0

        return {
            "usdt_balance": self.usdt_balance,
            "coin_balance": self.coin_balance,
            "coin_symbol": self.coin_symbol,
            "coin_value": coin_value,
            "total_value": total_value,
            "profit": profit,
            "profit_pct": profit_pct,
            "initial_balance": self.initial_balance,
        }

    def get_summary(self, current_price: float = 0) -> str:
        """生成账户摘要"""
        bal = self.get_balance(current_price)
        lines = [
            "=" * 50,
            "  模拟盘账户摘要",
            "=" * 50,
            f"  初始资金:     {bal['initial_balance']:>12.2f} USDT",
            f"  USDT 余额:    {bal['usdt_balance']:>12.2f} USDT",
            f"  持仓数量:     {bal['coin_balance']:>12.6f} {bal['coin_symbol']}",
            f"  持仓价值:     {bal['coin_value']:>12.2f} USDT",
            "-" * 50,
            f"  总资产:       {bal['total_value']:>12.2f} USDT",
            f"  总盈亏:       {bal['profit']:>+12.2f} USDT ({bal['profit_pct']:+.2f}%)",
            f"  交易次数:     {len(self.trades):>12d}",
            "=" * 50,
        ]
        return "\n".join(lines)
