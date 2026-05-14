"""
模拟盘交易所
"""
from utils.logger import get_logger

logger = get_logger("exchange.paper")


class PaperExchange:
    """模拟盘交易所"""

    def __init__(self, initial_balance: float = 10000.0, fee_rate: float = 0.001, slippage_pct: float = 0.05):
        self.initial_balance = initial_balance
        self.fee_rate = fee_rate
        self.slippage_pct = slippage_pct
        self.cash = initial_balance
        self.coin = 0.0
        self.trades = []
        self.buy_price = 0.0

    def buy(self, symbol: str, price: float, amount_pct: float = 0.3) -> dict | None:
        """买入"""
        if self.cash <= 0:
            return None
        cost = self.cash * amount_pct
        fee = cost * self.fee_rate
        actual_cost = cost - fee
        slippage = price * (self.slippage_pct / 100)
        actual_price = price + slippage
        coin_amount = actual_cost / actual_price

        self.cash -= cost
        self.coin += coin_amount
        self.buy_price = actual_price

        trade = {
            "timestamp": 0,
            "side": "buy",
            "price": round(actual_price, 2),
            "amount": coin_amount,
            "fee": round(fee, 4),
            "total": round(cost, 2),
        }
        self.trades.append(trade)
        return trade

    def sell(self, symbol: str, price: float, amount: float = 0.0) -> dict | None:
        """卖出"""
        if self.coin <= 0:
            return None
        sell_amount = amount if amount > 0 else self.coin
        slippage = price * (self.slippage_pct / 100)
        actual_price = price - slippage
        revenue = sell_amount * actual_price
        fee = revenue * self.fee_rate
        actual_revenue = revenue - fee

        profit = actual_revenue - (sell_amount * self.buy_price) if self.buy_price > 0 else 0
        profit_pct = (profit / (sell_amount * self.buy_price) * 100) if self.buy_price > 0 else 0

        self.cash += actual_revenue
        self.coin -= sell_amount

        trade = {
            "timestamp": 0,
            "side": "sell",
            "price": round(actual_price, 2),
            "amount": sell_amount,
            "fee": round(fee, 4),
            "total": round(revenue, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2),
        }
        self.trades.append(trade)
        return trade

    def get_balance(self, price: float = 0.0) -> dict:
        """获取余额"""
        total_value = self.cash + self.coin * price
        profit = total_value - self.initial_balance
        profit_pct = (profit / self.initial_balance * 100) if self.initial_balance > 0 else 0
        return {
            "cash": round(self.cash, 2),
            "coin": round(self.coin, 6),
            "total_value": round(total_value, 2),
            "profit": round(profit, 2),
            "profit_pct": round(profit_pct, 2),
        }
