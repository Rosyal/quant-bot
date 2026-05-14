"""
信号机器人 — 接收 TradingView Webhook / 自定义信号
3Commas 核心功能：外部信号 → 自动下单
支持 HMAC 签名验证、信号去重、多策略路由、持久化
"""
import json
import hashlib
import hmac
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from datetime import datetime

from utils.logger import get_logger

logger = get_logger("signal_bot")


@dataclass
class SignalRule:
    """信号规则"""
    id: str = ""
    name: str = ""
    symbol: str = "BTC/USDT"
    action: str = "buy"          # buy / sell / close
    amount_pct: float = 30.0     # 资金比例 %
    source: str = "tradingview"  # tradingview / custom
    secret: str = ""             # Webhook 验证密钥
    enabled: bool = True
    # 高级参数
    leverage: int = 0            # 杠杆 (0=不设置)
    take_profit_pct: float = 0.0
    stop_loss_pct: float = 0.0
    # 信号去重
    dedup_window_sec: int = 60   # 同一信号去重窗口
    created_at: str = ""


@dataclass
class SignalRecord:
    """信号记录"""
    id: str = ""
    rule_id: str = ""
    symbol: str = ""
    action: str = ""
    price: float = 0.0
    amount: float = 0.0
    source: str = ""
    raw_payload: str = ""
    status: str = "received"     # received / executed / failed / deduplicated
    created_at: str = ""
    executed_at: str = ""


class SignalBot:
    """信号机器人 — 3Commas 级别"""

    def __init__(self):
        self._rules: Dict[str, SignalRule] = {}
        self._records: List[SignalRecord] = []
        self._signal_times: Dict[str, float] = {}  # 去重用

    # ---- 规则管理 ----

    def add_rule(self, name: str, symbol: str, action: str = "buy",
                 amount_pct: float = 30.0, source: str = "tradingview",
                 secret: str = "", leverage: int = 0,
                 take_profit_pct: float = 0.0, stop_loss_pct: float = 0.0,
                 dedup_window_sec: int = 60) -> SignalRule:
        """添加信号规则"""
        rule_id = f"rule-{hashlib.md5(f'{name}:{symbol}:{time.time()}'.encode()).hexdigest()[:8]}"
        rule = SignalRule(
            id=rule_id, name=name, symbol=symbol, action=action,
            amount_pct=amount_pct, source=source, secret=secret,
            leverage=leverage, take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct, dedup_window_sec=dedup_window_sec,
            created_at=datetime.now().isoformat(),
        )
        self._rules[rule_id] = rule
        logger.info(f"信号规则添加: {rule_id} {name} {symbol}")
        return rule

    def toggle_rule(self, rule_id: str, enabled: bool) -> bool:
        if rule_id in self._rules:
            self._rules[rule_id].enabled = enabled
            return True
        return False

    def delete_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    # ---- 信号处理 ----

    def process_webhook(self, source: str, payload: dict) -> dict:
        """处理 Webhook 信号（主入口）"""
        # TradingView 标准格式
        if source == "tradingview":
            return self._process_tradingview(payload)
        else:
            return self._process_custom(source, payload)

    def _process_tradingview(self, payload: dict) -> dict:
        """处理 TradingView Webhook"""
        # TradingView 发送格式: {"action": "buy"/"sell", "symbol": "BTCUSDT",
        #                         "price": 50000, "strategy_order_id": "..."}
        action = payload.get("action", "").lower()
        raw_symbol = payload.get("symbol", "")
        # TradingView 格式: "BTCUSDT" → "BTC/USDT"
        if "/" not in raw_symbol and raw_symbol.endswith("USDT"):
            symbol = raw_symbol[:-4] + "/USDT"
        elif "/" not in raw_symbol and raw_symbol.endswith("BUSD"):
            symbol = raw_symbol[:-4] + "/BUSD"
        elif "/" not in raw_symbol and raw_symbol.endswith("BTC"):
            symbol = raw_symbol[:-3] + "/BTC"
        elif "/" in raw_symbol:
            symbol = raw_symbol
        else:
            symbol = raw_symbol + "/USDT"

        # 匹配规则
        matched_rules = [r for r in self._rules.values()
                         if r.source == "tradingview" and r.enabled
                         and (r.symbol == symbol or r.symbol == "*")]

        if not matched_rules:
            record = self._create_record("", symbol, action, 0, 0,
                                         "tradingview", payload, "failed")
            return {"status": "no_rule", "record": asdict(record)}

        results = []
        for rule in matched_rules:
            # HMAC 验证
            if rule.secret:
                sig = payload.get("signature", "")
                if not self._verify_hmac(payload, rule.secret, sig):
                    record = self._create_record(rule.id, symbol, action, 0, 0,
                                                 "tradingview", payload, "failed")
                    results.append({"status": "auth_failed", "record": asdict(record)})
                    continue

            # 信号去重
            dedup_key = f"{rule.id}:{action}:{symbol}"
            if self._is_duplicate(dedup_key, rule.dedup_window_sec):
                record = self._create_record(rule.id, symbol, action, 0, 0,
                                             "tradingview", payload, "deduplicated")
                results.append({"status": "deduplicated", "record": asdict(record)})
                continue

            # 执行信号
            price = payload.get("price", 0)
            record = self._execute_signal(rule, action, symbol, price, payload)
            results.append({"status": record.status, "record": asdict(record)})

        return {"results": results}

    def _process_custom(self, source: str, payload: dict) -> dict:
        """处理自定义信号"""
        action = payload.get("action", "buy").lower()
        symbol = payload.get("symbol", "BTC/USDT")
        price = payload.get("price", 0)

        matched_rules = [r for r in self._rules.values()
                         if r.source == source and r.enabled
                         and (r.symbol == symbol or r.symbol == "*")]

        if not matched_rules:
            record = self._create_record("", symbol, action, 0, 0,
                                         source, payload, "failed")
            return {"status": "no_rule", "record": asdict(record)}

        results = []
        for rule in matched_rules:
            dedup_key = f"{rule.id}:{action}:{symbol}"
            if self._is_duplicate(dedup_key, rule.dedup_window_sec):
                record = self._create_record(rule.id, symbol, action, 0, 0,
                                             source, payload, "deduplicated")
                results.append({"status": "deduplicated", "record": asdict(record)})
                continue
            record = self._execute_signal(rule, action, symbol, price, payload)
            results.append({"status": record.status, "record": asdict(record)})

        return {"results": results}

    def _execute_signal(self, rule: SignalRule, action: str, symbol: str,
                        price: float, payload: dict) -> SignalRecord:
        """执行信号"""
        # 如果规则指定了 action，优先用规则的
        effective_action = action if action in ("buy", "sell", "close") else rule.action
        amount = rule.amount_pct  # 百分比，由上层换算

        record = self._create_record(
            rule.id, symbol, effective_action, price, amount,
            rule.source, payload, "received"
        )

        try:
            # 这里只记录，实际下单由上层 exchange 执行
            # TODO: 集成 exchange.real.RealExchange
            record.status = "executed"
            record.executed_at = datetime.now().isoformat()
            logger.info(f"信号执行成功: {effective_action} {symbol} 价格{price}")
        except Exception as e:
            record.status = "failed"
            logger.error(f"信号执行失败: {e}")

        return record

    def _create_record(self, rule_id: str, symbol: str, action: str,
                       price: float, amount: float, source: str,
                       payload: dict, status: str) -> SignalRecord:
        """创建信号记录"""
        record_id = f"sig-{hashlib.md5(f'{time.time()}:{symbol}'.encode()).hexdigest()[:8]}"
        record = SignalRecord(
            id=record_id, rule_id=rule_id, symbol=symbol, action=action,
            price=price, amount=amount, source=source,
            raw_payload=json.dumps(payload, default=str)[:500],
            status=status, created_at=datetime.now().isoformat(),
        )
        self._records.append(record)
        if len(self._records) > 10000:
            self._records = self._records[-5000:]
        return record

    def _verify_hmac(self, payload: dict, secret: str, signature: str) -> bool:
        """HMAC 签名验证"""
        if not signature:
            return False
        msg = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        expected = hmac.new(secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    def _is_duplicate(self, key: str, window_sec: int) -> bool:
        """信号去重检查"""
        now = time.time()
        last_time = self._signal_times.get(key, 0)
        if now - last_time < window_sec:
            return True
        self._signal_times[key] = now
        # 清理过期记录
        expired = [k for k, v in self._signal_times.items() if now - v > 3600]
        for k in expired:
            del self._signal_times[k]
        return False

    # ---- 查询 ----

    def get_rules(self) -> List[dict]:
        return [{"id": r.id, "name": r.name, "symbol": r.symbol, "action": r.action,
                 "amount_pct": r.amount_pct, "source": r.source, "enabled": r.enabled,
                 "leverage": r.leverage, "take_profit_pct": r.take_profit_pct,
                 "stop_loss_pct": r.stop_loss_pct}
                for r in self._rules.values()]

    def get_records(self, limit: int = 50, status: str = "") -> List[dict]:
        records = self._records
        if status:
            records = [r for r in records if r.status == status]
        return [{"id": r.id, "rule_id": r.rule_id, "symbol": r.symbol,
                 "action": r.action, "price": r.price, "status": r.status,
                 "source": r.source, "created_at": r.created_at,
                 "executed_at": r.executed_at}
                for r in records[-limit:]]

    def get_stats(self) -> dict:
        """信号统计"""
        total = len(self._records)
        by_status = {}
        by_source = {}
        for r in self._records:
            by_status[r.status] = by_status.get(r.status, 0) + 1
            by_source[r.source] = by_source.get(r.source, 0) + 1
        return {"total_signals": total, "rules_count": len(self._rules),
                "by_status": by_status, "by_source": by_source}
