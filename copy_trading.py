"""
跟单交易 — 订阅高手策略信号，自动跟单
差异化功能：社交交易 / Copy Trading
支持：比例跟单/固定金额跟单、风控限制、实时同步、持久化
"""
import time
import json
import os
import hashlib
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

from utils.logger import get_logger

logger = get_logger("copy_trading")

COPY_TRADE_DIR = "data/copy_trading"


@dataclass
class CopyTrader:
    """被跟单的交易员"""
    id: str = ""
    name: str = ""
    strategy: str = ""
    win_rate: float = 0.0
    total_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    followers: int = 0
    trades_count: int = 0
    # 高级指标
    sharpe_ratio: float = 0.0
    avg_holding_hours: float = 0.0
    preferred_symbols: List[str] = field(default_factory=list)
    risk_level: str = "medium"  # low / medium / high
    created_at: str = ""


@dataclass
class CopySubscription:
    """跟单订阅"""
    user: str = ""
    trader_id: str = ""
    amount_pct: float = 10.0  # 跟单资金比例 %
    max_loss_pct: float = 5.0  # 单笔最大亏损 %
    # 高级参数
    copy_mode: str = "proportional"  # proportional / fixed
    fixed_amount: float = 0.0        # 固定金额模式下的金额
    max_positions: int = 5           # 最大同时持仓
    copy_sl: bool = True             # 跟随止损
    copy_tp: bool = True             # 跟随止盈
    skip_symbols: List[str] = field(default_factory=list)  # 排除的交易对
    active: bool = True
    created_at: str = ""


@dataclass
class CopyTradeRecord:
    """跟单交易记录"""
    id: str = ""
    trader_id: str = ""
    follower: str = ""
    symbol: str = ""
    side: str = ""
    price: float = 0.0
    amount: float = 0.0
    profit: float = 0.0
    status: str = "open"  # open / closed
    opened_at: str = ""
    closed_at: str = ""


class CopyTradingService:
    """跟单交易服务 — 3Commas/eToro 级别"""

    def __init__(self, data_dir: str = COPY_TRADE_DIR):
        self.data_dir = data_dir
        self._traders: Dict[str, CopyTrader] = {}
        self._subs: List[CopySubscription] = []
        self._records: List[CopyTradeRecord] = []
        self._load()

    # ---- 交易员管理 ----

    def register_trader(self, name: str, strategy: str = "",
                        risk_level: str = "medium",
                        preferred_symbols: List[str] = None) -> CopyTrader:
        """注册交易员"""
        tid = hashlib.md5(f"trader:{name}:{time.time()}".encode()).hexdigest()[:10]
        trader = CopyTrader(
            id=tid, name=name, strategy=strategy,
            risk_level=risk_level,
            preferred_symbols=preferred_symbols or [],
            created_at=datetime.now().isoformat(),
        )
        self._traders[tid] = trader
        self._save()
        logger.info(f"交易员注册: {tid} {name}")
        return trader

    def update_trader_stats(self, trader_id: str, win_rate: float = None,
                            total_return_pct: float = None,
                            max_drawdown_pct: float = None,
                            sharpe_ratio: float = None,
                            trades_count: int = None):
        """更新交易员统计"""
        if trader_id not in self._traders:
            return
        t = self._traders[trader_id]
        if win_rate is not None:
            t.win_rate = win_rate
        if total_return_pct is not None:
            t.total_return_pct = total_return_pct
        if max_drawdown_pct is not None:
            t.max_drawdown_pct = max_drawdown_pct
        if sharpe_ratio is not None:
            t.sharpe_ratio = sharpe_ratio
        if trades_count is not None:
            t.trades_count = trades_count
        self._save()

    # ---- 订阅管理 ----

    def subscribe(self, user: str, trader_id: str,
                  amount_pct: float = 10.0, max_loss_pct: float = 5.0,
                  copy_mode: str = "proportional", fixed_amount: float = 0.0,
                  max_positions: int = 5, copy_sl: bool = True, copy_tp: bool = True,
                  skip_symbols: List[str] = None) -> Optional[CopySubscription]:
        """订阅跟单"""
        if trader_id not in self._traders:
            return None
        # 检查是否已订阅
        existing = [s for s in self._subs if s.user == user and s.trader_id == trader_id and s.active]
        if existing:
            logger.warning(f"{user} 已订阅 {trader_id}")
            return existing[0]

        sub = CopySubscription(
            user=user, trader_id=trader_id,
            amount_pct=amount_pct, max_loss_pct=max_loss_pct,
            copy_mode=copy_mode, fixed_amount=fixed_amount,
            max_positions=max_positions, copy_sl=copy_sl, copy_tp=copy_tp,
            skip_symbols=skip_symbols or [],
            active=True, created_at=datetime.now().isoformat(),
        )
        self._subs.append(sub)
        self._traders[trader_id].followers += 1
        self._save()
        logger.info(f"跟单订阅: {user} → {trader_id}")
        return sub

    def unsubscribe(self, user: str, trader_id: str) -> bool:
        """取消订阅"""
        for sub in self._subs:
            if sub.user == user and sub.trader_id == trader_id and sub.active:
                sub.active = False
                if trader_id in self._traders:
                    self._traders[trader_id].followers = max(0, self._traders[trader_id].followers - 1)
                self._save()
                return True
        return False

    # ---- 信号同步 ----

    def on_trader_signal(self, trader_id: str, symbol: str, side: str,
                         price: float, amount: float,
                         stop_loss: float = 0, take_profit: float = 0) -> List[Dict]:
        """交易员下单 → 触发跟单"""
        if trader_id not in self._traders:
            return []

        results = []
        for sub in self._subs:
            if not sub.active or sub.trader_id != trader_id:
                continue

            # 排除交易对
            if symbol in sub.skip_symbols:
                continue

            # 检查最大持仓
            open_positions = [r for r in self._records
                              if r.follower == sub.user and r.status == "open"]
            if len(open_positions) >= sub.max_positions:
                continue

            # 计算跟单金额
            if sub.copy_mode == "fixed":
                copy_amount = sub.fixed_amount / price if price > 0 else 0
            else:  # proportional
                copy_amount = amount * sub.amount_pct / 100

            if copy_amount <= 0:
                continue

            # 记录跟单
            record = self.record_copy_trade(
                trader_id, sub.user, symbol, side, price, copy_amount
            )

            # 风控检查
            if sub.max_loss_pct > 0 and stop_loss > 0 and price > 0:
                max_loss_amount = sub.max_loss_pct / 100 * copy_amount * price
                actual_loss = (price - stop_loss) * copy_amount if side == "buy" else (stop_loss - price) * copy_amount
                if actual_loss > max_loss_amount:
                    # 缩减仓位
                    copy_amount = copy_amount * max_loss_amount / actual_loss if actual_loss > 0 else copy_amount

            results.append({
                "follower": sub.user,
                "symbol": symbol,
                "side": side,
                "price": price,
                "amount": round(copy_amount, 8),
                "stop_loss": stop_loss if sub.copy_sl else 0,
                "take_profit": take_profit if sub.copy_tp else 0,
                "record_id": record.id,
            })

        return results

    def on_trader_close(self, trader_id: str, symbol: str, price: float,
                        profit: float = 0.0) -> List[Dict]:
        """交易员平仓 → 触发跟单平仓"""
        results = []
        for record in self._records:
            if record.trader_id != trader_id or record.symbol != symbol or record.status != "open":
                continue
            record.status = "closed"
            record.closed_at = datetime.now().isoformat()
            # 按比例计算利润
            record.profit = profit * (record.amount / max(amount, 1)) if profit != 0 else 0
            results.append({
                "follower": record.follower,
                "symbol": symbol,
                "close_price": price,
                "profit": round(record.profit, 2),
            })
        if results:
            self._save()
        return results

    # ---- 记录与查询 ----

    def record_copy_trade(self, trader_id: str, follower: str, symbol: str,
                          side: str, price: float, amount: float, profit: float = 0.0) -> CopyTradeRecord:
        tid = hashlib.md5(f"{trader_id}:{time.time()}".encode()).hexdigest()[:10]
        rec = CopyTradeRecord(
            id=tid, trader_id=trader_id, follower=follower,
            symbol=symbol, side=side, price=price,
            amount=amount, profit=profit,
            opened_at=datetime.now().isoformat(),
        )
        self._records.append(rec)
        self._save()
        return rec

    def get_traders(self, sort_by: str = "win_rate", limit: int = 20) -> List[dict]:
        """获取交易员排行"""
        traders = list(self._traders.values())
        sort_key = {
            "win_rate": lambda t: t.win_rate,
            "return": lambda t: t.total_return_pct,
            "sharpe": lambda t: t.sharpe_ratio,
            "followers": lambda t: t.followers,
        }.get(sort_by, lambda t: t.win_rate)
        traders.sort(key=sort_key, reverse=True)
        return [asdict(t) for t in traders[:limit]]

    def get_subscriptions(self, user: str) -> List[dict]:
        return [asdict(s) for s in self._subs if s.user == user and s.active]

    def get_copy_pnl(self, user: str) -> dict:
        user_records = [r for r in self._records if r.follower == user]
        closed = [r for r in user_records if r.status == "closed"]
        total_profit = sum(r.profit for r in closed)
        wins = sum(1 for r in closed if r.profit > 0)
        return {
            "total_trades": len(user_records),
            "closed_trades": len(closed),
            "open_trades": len([r for r in user_records if r.status == "open"]),
            "total_profit": round(total_profit, 2),
            "win_rate": round(wins / len(closed) * 100, 1) if closed else 0,
        }

    def get_open_positions(self, user: str) -> List[dict]:
        """获取用户当前跟单持仓"""
        return [asdict(r) for r in self._records
                if r.follower == user and r.status == "open"]

    # ---- 持久化 ----

    def _save(self):
        os.makedirs(self.data_dir, exist_ok=True)
        data = {
            "traders": {tid: asdict(t) for tid, t in self._traders.items()},
            "subscriptions": [asdict(s) for s in self._subs],
            "records": [asdict(r) for r in self._records[-5000:]],  # 最多保留5000条
        }
        path = os.path.join(self.data_dir, "copy_trading.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _load(self):
        path = os.path.join(self.data_dir, "copy_trading.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for tid, td in data.get("traders", {}).items():
                self._traders[tid] = CopyTrader(**td)
            for sd in data.get("subscriptions", []):
                self._subs.append(CopySubscription(**sd))
            for rd in data.get("records", []):
                self._records.append(CopyTradeRecord(**rd))
        except Exception as e:
            logger.error(f"加载跟单数据失败: {e}")
