"""
SQLite 数据库管理
负责所有数据的存储和查询
"""
from __future__ import annotations

import sqlite3
import os
from datetime import datetime
from utils.logger import get_logger
from config import DB_PATH

logger = get_logger("db")


class Database:
    def __init__(self, db_path: str = DB_PATH):
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()
        logger.info(f"数据库已连接: {db_path}")

    def _init_tables(self):
        """初始化数据库表"""
        cursor = self.conn.cursor()

        # K线数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                UNIQUE(symbol, timeframe, timestamp)
            )
        """)

        # 交易记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL,
                total REAL NOT NULL,
                timestamp INTEGER NOT NULL,
                strategy TEXT NOT NULL,
                profit REAL,
                profit_pct REAL
            )
        """)

        # 账户快照表 (用于追踪资金曲线)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS balance_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                usdt_balance REAL NOT NULL,
                coin_balance REAL NOT NULL,
                coin_symbol TEXT NOT NULL,
                total_value REAL NOT NULL
            )
        """)

        # 创建索引加速查询
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_tf_ts
            ON ohlcv(symbol, timeframe, timestamp)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts
            ON trades(symbol, timestamp)
        """)

        self.conn.commit()

    # ============ K线数据 ============

    def save_ohlcv(self, symbol: str, timeframe: str, candles: list[dict]):
        """批量保存K线数据"""
        cursor = self.conn.cursor()
        rows = []
        for c in candles:
            rows.append((
                symbol, timeframe, c["timestamp"],
                c["open"], c["high"], c["low"], c["close"], c["volume"]
            ))
        cursor.executemany(
            """INSERT OR REPLACE INTO ohlcv
               (symbol, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()
        logger.info(f"保存 {len(rows)} 条K线数据 ({symbol} {timeframe})")

    def get_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 500
    ) -> list[dict]:
        """获取最近的K线数据"""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT timestamp, open, high, low, close, volume
               FROM ohlcv
               WHERE symbol = ? AND timeframe = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (symbol, timeframe, limit),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_ohlcv_count(self, symbol: str, timeframe: str) -> int:
        """获取K线数据条数"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM ohlcv WHERE symbol = ? AND timeframe = ?",
            (symbol, timeframe),
        )
        return cursor.fetchone()[0]

    def get_ohlcv_max_timestamp(self, symbol: str, timeframe: str) -> int | None:
        """最新一根 K 线的 unix 秒时间戳; 无数据返回 None"""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT MAX(timestamp) AS mx FROM ohlcv
               WHERE symbol = ? AND timeframe = ?""",
            (symbol, timeframe),
        )
        row = cursor.fetchone()
        if row is None or row["mx"] is None:
            return None
        return int(row["mx"])

    # ============ 交易记录 ============

    def save_trade(self, trade: dict):
        """保存交易记录"""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO trades
               (symbol, side, price, amount, fee, total, timestamp, strategy, profit, profit_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade["symbol"], trade["side"], trade["price"],
                trade["amount"], trade["fee"], trade["total"],
                trade["timestamp"], trade["strategy"],
                trade.get("profit"), trade.get("profit_pct"),
            ),
        )
        self.conn.commit()
        logger.info(
            f"交易记录已保存: {trade['side']} {trade['amount']:.6f} "
            f"{trade['symbol']} @ {trade['price']:.2f}"
        )

    def get_trades(self, symbol: str, limit: int = 50) -> list[dict]:
        """获取最近的交易记录"""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM trades
               WHERE symbol = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (symbol, limit),
        )
        return [dict(r) for r in reversed(cursor.fetchall())]

    def get_trade_stats(self, symbol: str) -> dict:
        """获取交易统计"""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN side='buy' THEN 1 ELSE 0 END) as buys,
                SUM(CASE WHEN side='sell' THEN 1 ELSE 0 END) as sells,
                SUM(fee) as total_fees,
                COALESCE(SUM(profit), 0) as total_profit,
                AVG(COALESCE(profit_pct, 0)) as avg_profit_pct
               FROM trades WHERE symbol = ?""",
            (symbol,),
        )
        return dict(cursor.fetchone())

    # ============ 账户快照 ============

    def save_balance_snapshot(self, snapshot: dict):
        """保存账户快照"""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO balance_snapshots
               (timestamp, usdt_balance, coin_balance, coin_symbol, total_value)
               VALUES (?, ?, ?, ?, ?)""",
            (
                snapshot["timestamp"],
                snapshot["usdt_balance"],
                snapshot["coin_balance"],
                snapshot["coin_symbol"],
                snapshot["total_value"],
            ),
        )
        self.conn.commit()

    def get_balance_history(self, limit: int = 500) -> list[dict]:
        """获取资金曲线"""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM balance_snapshots
               ORDER BY timestamp DESC LIMIT ?""",
            (limit,),
        )
        return [dict(r) for r in reversed(cursor.fetchall())]

    def close(self):
        """关闭数据库连接"""
        self.conn.close()
        logger.info("数据库连接已关闭")
