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

        # 消息池 (RSS 等): 分类/情绪辅助, 非投资建议
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                feed_url TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT,
                summary TEXT,
                published_at INTEGER NOT NULL,
                fetched_at INTEGER NOT NULL,
                category TEXT NOT NULL,
                sentiment TEXT NOT NULL,
                sentiment_score INTEGER NOT NULL DEFAULT 0,
                tags_json TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_published
            ON news_items(published_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_news_category
            ON news_items(category, published_at)
        """)

        # 审计事件 (机构化脚手架: 谁、何时、对何资源、结果); 非监管报送
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT,
                payload_json TEXT,
                outcome TEXT NOT NULL,
                latency_ms REAL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approval_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_ts INTEGER NOT NULL,
                requester TEXT NOT NULL,
                action TEXT NOT NULL,
                payload_json TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                decided_ts INTEGER,
                decided_by TEXT,
                note TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_approval_status
            ON approval_requests(status, created_ts)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fund_transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                from_account TEXT NOT NULL,
                to_account TEXT NOT NULL,
                amount_usdt REAL NOT NULL,
                note TEXT,
                ref TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_balances (
                account_id TEXT PRIMARY KEY,
                balance_usdt REAL NOT NULL DEFAULT 0
            )
        """)

        # OMS 模拟撮合回报 (逐笔 legs_json)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS oms_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                client_order_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                status TEXT NOT NULL,
                avg_px REAL,
                filled_qty REAL,
                fee_usdt REAL,
                latency_ns INTEGER,
                legs_json TEXT,
                detail_json TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_oms_exec_ts
            ON oms_executions(ts)
        """)

        # 净头寸 (现货简化; 非 CCP 多边清算)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clearing_net_positions (
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                qty REAL NOT NULL,
                avg_px REAL NOT NULL DEFAULT 0,
                updated_ts INTEGER NOT NULL,
                PRIMARY KEY (account_id, symbol)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clearing_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                label TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
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

    # ============ 消息池 ============

    def insert_news_item(self, row: dict) -> bool:
        """
        插入一条消息; content_hash 冲突则跳过。
        :return: True 表示新插入
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO news_items
               (content_hash, feed_url, title, link, summary, published_at,
                fetched_at, category, sentiment, sentiment_score, tags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["content_hash"],
                row["feed_url"],
                row["title"],
                row.get("link") or "",
                row.get("summary") or "",
                int(row["published_at"]),
                int(row["fetched_at"]),
                row["category"],
                row["sentiment"],
                int(row["sentiment_score"]),
                row.get("tags_json") or "[]",
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def list_news_items(
        self,
        *,
        limit: int = 50,
        since_ts: int | None = None,
        category: str | None = None,
    ) -> list[dict]:
        cursor = self.conn.cursor()
        q = "SELECT * FROM news_items WHERE 1=1"
        params: list = []
        if since_ts is not None:
            q += " AND published_at >= ?"
            params.append(since_ts)
        if category:
            q += " AND category = ?"
            params.append(category.strip().lower())
        q += " ORDER BY published_at DESC LIMIT ?"
        params.append(limit)
        cursor.execute(q, params)
        return [dict(r) for r in cursor.fetchall()]

    def count_news_since(self, since_ts: int) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) AS c FROM news_items WHERE published_at >= ?",
            (since_ts,),
        )
        return int(cursor.fetchone()["c"])

    # ============ 审计 (合规脚手架) ============

    def insert_audit_event(self, row: dict) -> int:
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO audit_events
               (ts, actor, action, resource, payload_json, outcome, latency_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                int(row["ts"]),
                row["actor"],
                row["action"],
                row.get("resource") or "",
                row.get("payload_json") or "",
                row["outcome"],
                row.get("latency_ms"),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_audit_events(self, limit: int = 100) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",
            (max(1, min(2000, limit)),),
        )
        return [dict(r) for r in cursor.fetchall()]

    # ============ 审批流 ============

    def insert_approval_request(
        self,
        *,
        requester: str,
        action: str,
        payload_json: str = "",
    ) -> int:
        import time

        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO approval_requests
               (created_ts, requester, action, payload_json, status)
               VALUES (?, ?, ?, ?, 'pending')""",
            (int(time.time()), requester, action, payload_json),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_approval_requests(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        cursor = self.conn.cursor()
        if status:
            cursor.execute(
                """SELECT * FROM approval_requests
                   WHERE status = ? ORDER BY id DESC LIMIT ?""",
                (status, max(1, min(500, limit))),
            )
        else:
            cursor.execute(
                "SELECT * FROM approval_requests ORDER BY id DESC LIMIT ?",
                (max(1, min(500, limit)),),
            )
        return [dict(r) for r in cursor.fetchall()]

    def get_approval_request(self, req_id: int) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM approval_requests WHERE id = ?", (req_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def resolve_approval_request(
        self,
        req_id: int,
        *,
        new_status: str,
        decided_by: str,
        note: str = "",
    ) -> bool:
        import time

        if new_status not in ("approved", "rejected"):
            return False
        cursor = self.conn.cursor()
        cursor.execute(
            """UPDATE approval_requests SET status = ?, decided_ts = ?,
               decided_by = ?, note = ? WHERE id = ? AND status = 'pending'""",
            (new_status, int(time.time()), decided_by, note, req_id),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # ============ 多账户账本 ============

    def ensure_account_balance(self, account_id: str, initial_if_missing: float = 0.0) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT OR IGNORE INTO account_balances (account_id, balance_usdt)
               VALUES (?, ?)""",
            (account_id, float(initial_if_missing)),
        )
        self.conn.commit()

    def get_account_balance(self, account_id: str) -> float:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT balance_usdt FROM account_balances WHERE account_id = ?",
            (account_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return 0.0
        return float(row["balance_usdt"])

    def execute_transfer(
        self,
        from_account: str,
        to_account: str,
        amount_usdt: float,
        *,
        note: str = "",
        ref: str = "",
    ) -> dict:
        import time

        if amount_usdt <= 0:
            raise ValueError("amount_usdt 须为正")
        if from_account == to_account:
            raise ValueError("划出与划入账户不能相同")
        cur = self.conn.cursor()
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            for aid in (from_account, to_account):
                cur.execute(
                    """INSERT OR IGNORE INTO account_balances (account_id, balance_usdt)
                       VALUES (?, 0)""",
                    (aid,),
                )
            cur.execute(
                "SELECT balance_usdt FROM account_balances WHERE account_id = ?",
                (from_account,),
            )
            row = cur.fetchone()
            from_bal = float(row["balance_usdt"]) if row else 0.0
            if from_bal < amount_usdt:
                self.conn.rollback()
                return {"ok": False, "reason": "余额不足"}

            cur.execute(
                "SELECT balance_usdt FROM account_balances WHERE account_id = ?",
                (to_account,),
            )
            row2 = cur.fetchone()
            to_bal = float(row2["balance_usdt"]) if row2 else 0.0

            cur.execute(
                "UPDATE account_balances SET balance_usdt = ? WHERE account_id = ?",
                (from_bal - amount_usdt, from_account),
            )
            cur.execute(
                "UPDATE account_balances SET balance_usdt = ? WHERE account_id = ?",
                (to_bal + amount_usdt, to_account),
            )
            ts = int(time.time())
            cur.execute(
                """INSERT INTO fund_transfers
                   (ts, from_account, to_account, amount_usdt, note, ref)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ts, from_account, to_account, amount_usdt, note, ref),
            )
            self.conn.commit()
            return {"ok": True, "ts": ts, "amount": amount_usdt}
        except Exception:
            self.conn.rollback()
            raise

    def list_fund_transfers(self, limit: int = 50) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM fund_transfers ORDER BY id DESC LIMIT ?",
            (max(1, min(500, limit)),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def list_sell_trades(self, limit: int = 50000) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM trades WHERE side = 'sell'
               ORDER BY timestamp ASC LIMIT ?""",
            (max(1, min(200000, limit)),),
        )
        return [dict(r) for r in cursor.fetchall()]

    # ============ OMS 撮合回报 / 净额清算 ============

    def insert_oms_execution(self, row: dict) -> int:
        import time

        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO oms_executions
               (ts, client_order_id, account_id, symbol, side, status,
                avg_px, filled_qty, fee_usdt, latency_ns, legs_json, detail_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                int(row.get("ts") or time.time()),
                row["client_order_id"],
                row["account_id"],
                row["symbol"],
                row["side"],
                row["status"],
                row.get("avg_px"),
                row.get("filled_qty"),
                row.get("fee_usdt"),
                int(row["latency_ns"]) if row.get("latency_ns") is not None else None,
                row.get("legs_json") or "[]",
                row.get("detail_json") or "{}",
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def list_oms_executions(self, limit: int = 50) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM oms_executions ORDER BY id DESC LIMIT ?",
            (max(1, min(500, limit)),),
        )
        return [dict(r) for r in cursor.fetchall()]

    def get_net_position(self, account_id: str, symbol: str) -> dict | None:
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT * FROM clearing_net_positions
               WHERE account_id = ? AND symbol = ?""",
            (account_id, symbol),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def upsert_net_position(
        self,
        *,
        account_id: str,
        symbol: str,
        qty: float,
        avg_px: float,
        updated_ts: int,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO clearing_net_positions
               (account_id, symbol, qty, avg_px, updated_ts)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(account_id, symbol) DO UPDATE SET
                 qty = excluded.qty,
                 avg_px = excluded.avg_px,
                 updated_ts = excluded.updated_ts""",
            (account_id, symbol, qty, avg_px, updated_ts),
        )
        self.conn.commit()

    def list_net_positions(self) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM clearing_net_positions ORDER BY account_id, symbol")
        return [dict(r) for r in cursor.fetchall()]

    def insert_clearing_batch(self, label: str, payload_json: str) -> int:
        import time

        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO clearing_batches (ts, label, payload_json)
               VALUES (?, ?, ?)""",
            (int(time.time()), label, payload_json),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def close(self):
        """关闭数据库连接"""
        self.conn.close()
        logger.info("数据库连接已关闭")
