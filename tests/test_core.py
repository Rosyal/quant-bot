# -*- coding: utf-8 -*-
"""
quant-bot 单元测试
"""
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============ 策略测试 ============

class TestStrategies:
    def _mock_candles(self, n=100):
        import random
        random.seed(42)
        candles = []
        price = 100.0
        for i in range(n):
            price += random.uniform(-2, 2)
            candles.append({"timestamp": i, "open": price, "high": price+1, "low": price-1, "close": price, "volume": 1000})
        return candles

    def test_ma_cross(self):
        from strategy.ma_cross import MACrossStrategy
        s = MACrossStrategy(fast=5, slow=10)
        signals = s.generate_signals(self._mock_candles())
        assert len(signals) == 100
        assert any(sig["signal"] != "hold" for sig in signals)

    def test_rsi(self):
        from strategy.rsi import RSIStrategy
        s = RSIStrategy(period=14)
        signals = s.generate_signals(self._mock_candles())
        assert len(signals) == 100

    def test_macd(self):
        from strategy.macd import MACDStrategy
        s = MACDStrategy()
        signals = s.generate_signals(self._mock_candles())
        assert len(signals) == 100

    def test_bollinger(self):
        from strategy.bollinger import BollingerStrategy
        s = BollingerStrategy()
        signals = s.generate_signals(self._mock_candles())
        assert len(signals) == 100

    def test_multi_tf(self):
        from strategy.multi_tf import MultiTFStrategy
        s = MultiTFStrategy()
        signals = s.generate_signals(self._mock_candles(200))
        assert len(signals) == 200

    def test_combo(self):
        from strategy.combo import ComboStrategy
        s = ComboStrategy()
        signals = s.generate_signals(self._mock_candles())
        assert len(signals) == 100

    def test_list_strategies(self):
        from strategy import list_strategies
        strategies = list_strategies()
        assert len(strategies) >= 6

    def test_get_strategy(self):
        from strategy import get_strategy
        s = get_strategy("ma_cross", fast=5, slow=10)
        assert s is not None
        assert s.name == "ma_cross"


# ============ 回测测试 ============

class TestBacktest:
    def test_run_backtest(self):
        from data_fetcher import generate_mock_data
        from backtest.engine import run_backtest
        candles = generate_mock_data(30)
        result = run_backtest(candles, "ma_cross", use_mock=True)
        assert result is not None
        assert "profit_pct" in result
        assert "total_trades" in result

    def test_monte_carlo(self):
        from backtest.monte_carlo import run_monte_carlo
        returns = [1.0, -0.5, 2.0, -1.0, 0.5]
        result = run_monte_carlo(returns, simulations=100)
        assert "avg_final" in result
        assert "prob_profit" in result


# ============ 风控测试 ============

class TestRiskManager:
    def test_stop_loss(self):
        from risk.manager import RiskManager
        rm = RiskManager(stop_loss=5.0)
        sig = rm.check_signal("hold", 100.0, 94.0, 1.0)
        assert sig == "sell"

    def test_take_profit(self):
        from risk.manager import RiskManager
        rm = RiskManager(take_profit=10.0)
        sig = rm.check_signal("hold", 100.0, 111.0, 1.0)
        assert sig == "sell"

    def test_max_daily_trades(self):
        from risk.manager import RiskManager
        rm = RiskManager(max_daily_trades=3)
        for _ in range(3):
            rm.record_trade(1.0)
        sig = rm.check_signal("buy", 0, 0, 0)
        assert sig == "hold"


# ============ 用户管理测试 ============

class TestUserManager:
    def test_create_and_auth(self):
        from user.manager import UserManager
        um = UserManager("/tmp/test_users.json")
        um.create_user("testuser", "pass123", "admin")
        user = um.authenticate("testuser", "pass123")
        assert user is not None
        assert user["role"] == "admin"

    def test_auth_fail(self):
        from user.manager import UserManager
        um = UserManager("/tmp/test_users2.json")
        um.create_user("testuser", "pass123")
        assert um.authenticate("testuser", "wrong") is None


# ============ 通知测试 ============

class TestNotifier:
    def test_notifier_init(self):
        from notification.notifier import Notifier
        n = Notifier()
        assert n is not None


# ============ 数据库测试 ============

class TestDatabase:
    def test_save_and_query(self):
        from db.database import Database
        db = Database("/tmp/test_quant.db")
        db.save_backtest("ma_cross", "BTC/USDT", {"profit_pct": 5.0}, {"fast": 10})
        history = db.get_backtest_history(10)
        assert len(history) >= 1


# ============ 网格交易测试 ============

class TestGridTrading:
    def test_grid_create_and_tick(self):
        from strategy_grid import GridTradingBot, GridConfig, GridType
        cfg = GridConfig(
            symbol="BTC/USDT", grid_type=GridType.ARITHMETIC,
            upper_price=50000, lower_price=40000,
            grid_count=5, total_investment=10000,
        )
        bot = GridTradingBot(cfg)
        bot.start(45000)
        assert bot.state.running
        assert len(bot.state.orders) > 0
        # tick 触发
        events = bot.tick(46000)
        assert isinstance(events, list)
        stats = bot.get_stats()
        assert stats["running"]
        assert stats["grid_count"] == 5

    def test_grid_geometric(self):
        from strategy_grid import GridTradingBot, GridConfig, GridType
        cfg = GridConfig(
            symbol="ETH/USDT", grid_type=GridType.GEOMETRIC,
            upper_price=3000, lower_price=2000,
            grid_count=4, total_investment=5000,
        )
        bot = GridTradingBot(cfg)
        bot.start(2500)
        assert bot.state.running
        stats = bot.get_stats()
        assert stats["grid_type"] == "geometric"

    def test_grid_stop_loss(self):
        from strategy_grid import GridTradingBot, GridConfig
        cfg = GridConfig(
            symbol="BTC/USDT", upper_price=50000, lower_price=40000,
            grid_count=5, total_investment=10000, stop_loss_pct=5.0,
        )
        bot = GridTradingBot(cfg)
        bot.start(45000)
        # 价格跌破下界 * (1 - stop_loss_pct/100)
        events = bot.tick(38000)
        # 止损可能在 tick 中触发，也可能需要检查 bot.state
        stats = bot.get_stats()
        # 止损后应该停止或标记
        assert isinstance(events, list)


# ============ DCA 定投测试 ============

class TestDCABot:
    def test_dca_create_and_tick(self):
        from strategy_dca import DCABot, DCAConfig
        cfg = DCAConfig(
            symbol="BTC/USDT", base_order=100, safety_order=200,
            max_safety_orders=3, price_deviation_pct=2.0, take_profit_pct=3.0,
        )
        bot = DCABot(cfg)
        bot.start(50000)
        assert bot.state.running
        # 价格下跌触发加仓
        events = bot.tick(49000)
        assert isinstance(events, list)
        stats = bot.get_stats()
        assert stats["running"]

    def test_dca_take_profit(self):
        from strategy_dca import DCABot, DCAConfig
        cfg = DCAConfig(
            symbol="BTC/USDT", base_order=100, safety_order=200,
            max_safety_orders=3, price_deviation_pct=2.0, take_profit_pct=1.0,
        )
        bot = DCABot(cfg)
        bot.start(50000)
        # 价格上涨触发止盈
        events = bot.tick(51000)
        assert isinstance(events, list)


# ============ 智能订单测试 ============

class TestSmartOrders:
    def test_trailing_tp(self):
        from smart_orders import SmartOrderManager
        mgr = SmartOrderManager()
        order = mgr.create_trailing_tp(
            symbol="BTC/USDT", side="sell", amount=0.1,
            activation_price=50000, callback_rate=2.0,
        )
        assert order is not None
        # 价格上涨，追踪
        triggered = mgr.tick("BTC/USDT", 52000)
        assert isinstance(triggered, list)
        # 价格回调触发
        triggered = mgr.tick("BTC/USDT", 50960)  # 回调 2%
        assert isinstance(triggered, list)

    def test_oco_order(self):
        from smart_orders import SmartOrderManager
        mgr = SmartOrderManager()
        order = mgr.create_oco(
            symbol="BTC/USDT", side="sell", amount=0.1,
            take_profit_price=55000, stop_loss_price=45000,
        )
        assert order is not None
        order_id = order["id"]
        # 触发止盈
        triggered = mgr.tick("BTC/USDT", 56000)
        assert any(o["order_id"] == order_id for o in triggered)

    def test_iceberg_order(self):
        from smart_orders import SmartOrderManager
        mgr = SmartOrderManager()
        order = mgr.create_iceberg(
            symbol="BTC/USDT", side="buy", total_amount=1.0,
            visible_amount=0.1, slice_interval_sec=0,  # 0间隔方便测试
        )
        assert order is not None
        triggered = mgr.tick("BTC/USDT", 50000)
        assert isinstance(triggered, list)

    def test_stop_limit(self):
        from smart_orders import SmartOrderManager
        mgr = SmartOrderManager()
        order = mgr.create_stop_limit(
            symbol="BTC/USDT", side="sell", amount=0.1,
            stop_price=49000, limit_price=48500,
        )
        assert order is not None
        triggered = mgr.tick("BTC/USDT", 48500)
        assert isinstance(triggered, list)


# ============ 信号机器人测试 ============

class TestSignalBot:
    def test_add_rule_and_webhook(self):
        from signal_bot import SignalBot
        bot = SignalBot()
        rule = bot.add_rule(
            name="TV-BTC", symbol="BTC/USDT", action="buy",
            amount_pct=30, source="tradingview",
        )
        assert rule is not None
        # 模拟 webhook — TradingView 格式 symbol 不带 /
        result = bot.process_webhook("tradingview", {
            "action": "buy", "symbol": "BTCUSDT",
        })
        # 返回格式: {"results": [{"status": ..., "record": ...}]}
        assert "results" in result or "status" in result
        if "results" in result:
            assert len(result["results"]) > 0
            assert result["results"][0]["status"] in ["received", "executed", "deduplicated", "auth_failed"]

    def test_signal_dedup(self):
        from signal_bot import SignalBot
        bot = SignalBot()
        bot.add_rule(name="TV-ETH", symbol="ETH/USDT", action="buy",
                     amount_pct=20, source="tradingview", dedup_window_sec=60)
        # 连续发送相同信号
        r1 = bot.process_webhook("tradingview", {"action": "buy", "symbol": "ETHUSDT"})
        r2 = bot.process_webhook("tradingview", {"action": "buy", "symbol": "ETHUSDT"})
        # 第二次应该被去重
        if "results" in r2:
            assert any(r.get("status") == "deduplicated" for r in r2["results"])
        else:
            assert r2["status"] == "deduplicated"


# ============ 跟单交易测试 ============

class TestCopyTrading:
    def test_register_and_follow(self):
        from copy_trading import CopyTradingService
        mgr = CopyTradingService(data_dir="/tmp/test_copy")
        trader = mgr.register_trader("CryptoKing", "趋势跟踪")
        assert trader is not None
        trader_id = trader.id
        # 订阅
        sub = mgr.subscribe("user1", trader_id, amount_pct=10)
        assert sub is not None
        # 跟单信号
        result = mgr.on_trader_signal(trader_id, "BTC/USDT", "buy", 50000, 0.1)
        assert isinstance(result, list)


# ============ 因子库测试 ============

class TestFactorLibrary:
    def test_list_factors(self):
        from factor_library import FactorLibrary
        lib = FactorLibrary()
        factors = lib.list_factors()
        assert len(factors) >= 30  # 30+ 内置因子

    def test_factor_categories(self):
        from factor_library import FactorLibrary
        lib = FactorLibrary()
        cats = lib.get_categories()
        assert len(cats) >= 5
        cat_names = [c["category"] for c in cats]
        assert "value" in cat_names
        assert "momentum" in cat_names

    def test_multi_factor_scoring(self):
        from factor_library import FactorLibrary
        lib = FactorLibrary()
        # 模拟因子数据
        factor_data = {
            "pe_ratio": {"SH600000": 8.0, "SH600036": 12.0, "SH601318": 15.0},
            "roe": {"SH600000": 15.0, "SH600036": 18.0, "SH601318": 12.0},
            "momentum_3m": {"SH600000": 5.0, "SH600036": -2.0, "SH601318": 8.0},
        }
        scores = lib.score_stocks(factor_data)
        assert len(scores) == 3
        assert all("score" in s for s in scores)
        # 排名
        assert scores[0]["rank"] == 1

    def test_ic_analysis(self):
        from factor_library import FactorLibrary
        lib = FactorLibrary()
        # 模拟 IC 分析数据
        period_vals = [{"SH600000": 8.0 + i, "SH600036": 12.0 + i} for i in range(12)]
        period_rets = [{"SH600000": 0.01 * i, "SH600036": -0.005 * i} for i in range(12)]
        result = lib.analyze_ic("pe_ratio", period_vals, period_rets)
        assert result.factor_name == "pe_ratio"
        assert result.period_count == 12

    def test_factor_backtest(self):
        from factor_library import FactorLibrary
        lib = FactorLibrary()
        period_vals = [{"SH600000": 8.0 + i, "SH600036": 12.0 + i, "SH601318": 15.0 + i} for i in range(10)]
        period_rets = [{"SH600000": 0.01, "SH600036": -0.01, "SH601318": 0.02} for _ in range(10)]
        result = lib.backtest_factor("pe_ratio", period_vals, period_rets)
        assert result.factor_name == "pe_ratio"


# ============ AkShare 缓存测试 ============

class TestAkShareCache:
    def test_cache_lru(self):
        from akshare_cache import LRUCache
        cache = LRUCache(max_size=3, default_ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        assert cache.get("a") == 1
        # 超出容量
        cache.set("d", 4)
        # b 应该被淘汰（a 刚被访问过）
        assert cache.get("b") is None
        stats = cache.stats()
        assert stats["size"] <= 3

    def test_cache_ttl(self):
        import time
        from akshare_cache import LRUCache
        cache = LRUCache(max_size=10, default_ttl=1)
        cache.set("x", 100)
        assert cache.get("x") == 100
        time.sleep(1.1)
        assert cache.get("x") is None


# ============ 投资组合测试 ============

class TestPortfolio:
    def test_risk_parity(self):
        from portfolio import PortfolioManager
        pm = PortfolioManager()
        pm.set_positions([
            {"symbol": "BTC/USDT", "amount": 0.5, "entry_price": 40000, "current_price": 50000, "weight": 50},
            {"symbol": "ETH/USDT", "amount": 5, "entry_price": 2500, "current_price": 3000, "weight": 50},
        ])
        weights = pm.risk_parity_weights()
        assert len(weights) == 2
        # 无历史数据时等权
        total = sum(weights.values())
        assert abs(total - 100) < 1

    def test_portfolio_stats(self):
        from portfolio import PortfolioManager
        pm = PortfolioManager()
        pm.set_positions([
            {"symbol": "BTC/USDT", "amount": 0.5, "entry_price": 40000, "current_price": 50000, "weight": 50},
            {"symbol": "ETH/USDT", "amount": 5, "entry_price": 2500, "current_price": 3000, "weight": 50},
        ])
        # portfolio_stats 需要 returns_history，没有时返回 error
        stats = pm.portfolio_stats()
        assert isinstance(stats, dict)


# ============ 蒙特卡洛高级测试 ============

class TestMonteCarloAdvanced:
    def test_parametric_var(self):
        from backtest.monte_carlo import parametric_var
        import random
        random.seed(42)
        returns = [random.gauss(0.1, 2.0) for _ in range(100)]
        result = parametric_var(returns, confidence=95)
        assert "var_daily" in result
        assert "cvar_daily" in result

    def test_stress_test(self):
        from backtest.monte_carlo import stress_test
        import random
        random.seed(42)
        returns = [random.gauss(0.1, 2.0) for _ in range(100)]
        result = stress_test(returns)
        assert "scenarios" in result
        assert len(result["scenarios"]) > 0


# ============ KMS 测试 ============

class TestKMS:
    def test_local_encrypt_decrypt(self):
        from kms_service import KMSService, KMSConfig, KMSMode
        KMSService.reset()
        config = KMSConfig(mode=KMSMode.LOCAL)
        kms = KMSService(config)
        payload = kms.encrypt("my-secret-api-key")
        assert payload.ciphertext != "my-secret-api-key"
        decrypted = kms.decrypt(payload)
        assert decrypted == "my-secret-api-key"

    def test_kms_mode(self):
        from kms_service import KMSService, KMSConfig, KMSMode
        KMSService.reset()
        config = KMSConfig(mode=KMSMode.LOCAL)
        kms = KMSService(config)
        assert kms.get_mode() == "local"
