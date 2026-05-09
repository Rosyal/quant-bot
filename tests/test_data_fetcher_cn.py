"""A股工具: 代码归一与 DataFrame 转换"""
from __future__ import annotations

import unittest

import pandas as pd

from data_fetcher_cn import akshare_df_to_candles, normalize_cn_symbol


class TestCnSymbol(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_cn_symbol("600519"), "600519")
        self.assertEqual(normalize_cn_symbol("600519.SH"), "600519")
        self.assertEqual(normalize_cn_symbol("sh600519"), "600519")
        self.assertEqual(normalize_cn_symbol("000001.SZ"), "000001")


class TestDfToCandles(unittest.TestCase):
    def test_daily_cn_columns(self):
        df = pd.DataFrame(
            {
                "日期": ["2024-01-02", "2024-01-03"],
                "开盘": [10.0, 10.5],
                "收盘": [10.4, 10.2],
                "最高": [10.6, 10.7],
                "最低": [9.9, 10.0],
                "成交量": [1000.0, 2000.0],
            }
        )
        c = akshare_df_to_candles(df)
        self.assertEqual(len(c), 2)
        self.assertIn("timestamp", c[0])
        self.assertEqual(c[0]["open"], 10.0)
        self.assertEqual(c[1]["close"], 10.2)


if __name__ == "__main__":
    unittest.main()
