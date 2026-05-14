"""
数据库模块 — SQLite
"""
import sqlite3
import json
import os
from datetime import datetime
from utils.logger import get_logger
from config import DB_PATH

logger = get_logger("db.database")


class Database:
    """SQLite 数据库管理"""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_tables()

    def _init_tables(self):
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                params TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                amount REAL,
                profit REAL,
                timestamp TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()

    def save_backtest(self, strategy: str, symbol: str, result: dict, params: dict = None):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO backtest_results (strategy, symbol, params, result_json) VALUES (?, ?, ?, ?)",
            (strategy, symbol, json.dumps(params or {}, ensure_ascii=False), json.dumps(result, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    def get_backtest_history(self, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM backtest_results ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [{"id": r["id"], "strategy": r["strategy"], "symbol": r["symbol"],
                 "params": json.loads(r["params"]) if r["params"] else {},
                 "result": json.loads(r["result_json"]), "created_at": r["created_at"]}
                for r in rows]

    def log_trade(self, strategy: str, symbol: str, side: str, price: float,
                  amount: float = 0, profit: float = 0):
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO trade_log (strategy, symbol, side, price, amount, profit) VALUES (?, ?, ?, ?, ?, ?)",
            (strategy, symbol, side, price, amount, profit),
        )
        conn.commit()
        conn.close()

    def get_trade_log(self, limit: int = 100) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM trade_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
