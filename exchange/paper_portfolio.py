"""
多交易对纸面账户: 共享 USDT, 每品种独立持仓数量, JSON 持久化
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

from config import FEE_RATE, PAPER_LIVE_STATE_PATH, INITIAL_BALANCE, SLIPPAGE_BPS
from utils.logger import get_logger

logger = get_logger("paper_portfolio")

_MAX_EQUITY_POINTS = 8000


class PaperPortfolio:
    def __init__(
        self,
        state_path: str = PAPER_LIVE_STATE_PATH,
        initial_usdt: float = INITIAL_BALANCE,
    ):
        self.state_path = state_path
        self.initial_usdt = initial_usdt
        self.usdt = initial_usdt
        self.positions: dict[str, float] = {}
        self.trades: list[dict[str, Any]] = []
        self.equity_curve: list[dict[str, Any]] = []
        # 边沿检测: key = "SYMBOL|strategy" -> 上一根已处理的 signal
        self.last_signals: dict[str, str] = {}
        self._load()

    @staticmethod
    def _exec_buy_price(reference_price: float, slippage_bps: float) -> float:
        return reference_price * (1.0 + slippage_bps / 10000.0)

    @staticmethod
    def _exec_sell_price(reference_price: float, slippage_bps: float) -> float:
        return max(reference_price * (1.0 - slippage_bps / 10000.0), 1e-12)

    def _load(self) -> None:
        if not os.path.isfile(self.state_path):
            return
        try:
            with open(self.state_path, encoding="utf-8") as f:
                data = json.load(f)
            self.usdt = float(data.get("usdt", self.initial_usdt))
            self.positions = {k: float(v) for k, v in data.get("positions", {}).items()}
            self.trades = list(data.get("trades", []))
            self.equity_curve = list(data.get("equity_curve", []))
            self.last_signals = dict(data.get("last_signals", {}))
            logger.info(f"已加载纸面账户: USDT={self.usdt:.2f}, 持仓数={len(self.positions)}")
        except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
            logger.warning(f"纸面状态加载失败, 使用初始资金: {e}")

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        tmp = self.state_path + ".tmp"
        payload = {
            "usdt": round(self.usdt, 8),
            "positions": {k: round(v, 10) for k, v in self.positions.items() if v > 0},
            "trades": self.trades[-2000:],
            "equity_curve": self.equity_curve[-_MAX_EQUITY_POINTS:],
            "last_signals": dict(self.last_signals),
            "updated_at": int(time.time()),
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_path)

    def total_equity(self, last_prices: dict[str, float]) -> float:
        total = self.usdt
        for sym, qty in self.positions.items():
            if qty <= 0:
                continue
            px = last_prices.get(sym)
            if px:
                total += qty * px
        return total

    def record_equity(self, ts: int, last_prices: dict[str, float]) -> None:
        eq = self.total_equity(last_prices)
        self.equity_curve.append({"t": ts, "equity": round(eq, 2)})
        if len(self.equity_curve) > _MAX_EQUITY_POINTS:
            self.equity_curve = self.equity_curve[-_MAX_EQUITY_POINTS:]

    def position_qty(self, symbol: str) -> float:
        return max(0.0, self.positions.get(symbol, 0.0))

    def buy(self, symbol: str, price: float, spend_usdt: float, strategy: str) -> dict | None:
        if spend_usdt <= 0 or price <= 0:
            return None
        if spend_usdt > self.usdt:
            spend_usdt = self.usdt
        if spend_usdt <= 0:
            return None
        exec_px = self._exec_buy_price(price, SLIPPAGE_BPS)
        fee = spend_usdt * FEE_RATE
        net = spend_usdt - fee
        qty = net / exec_px
        self.usdt -= spend_usdt
        self.positions[symbol] = self.positions.get(symbol, 0.0) + qty
        trade = {
            "symbol": symbol,
            "side": "buy",
            "price": exec_px,
            "amount": qty,
            "fee": fee,
            "total": spend_usdt,
            "timestamp": int(time.time()),
            "strategy": strategy,
        }
        self.trades.append(trade)
        logger.info(f"[纸面买入] {symbol} {qty:.6f} @ {exec_px:.4f}")
        return trade

    def sell_all(self, symbol: str, price: float, strategy: str) -> dict | None:
        qty = self.position_qty(symbol)
        if qty <= 0:
            return None
        exec_px = self._exec_sell_price(price, SLIPPAGE_BPS)
        gross = qty * exec_px
        fee = gross * FEE_RATE
        receive = gross - fee
        self.usdt += receive
        self.positions[symbol] = 0.0
        trade = {
            "symbol": symbol,
            "side": "sell",
            "price": exec_px,
            "amount": qty,
            "fee": fee,
            "total": receive,
            "timestamp": int(time.time()),
            "strategy": strategy,
        }
        self.trades.append(trade)
        logger.info(f"[纸面卖出] {symbol} {qty:.6f} @ {exec_px:.4f}")
        return trade
