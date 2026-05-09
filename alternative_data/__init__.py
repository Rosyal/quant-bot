"""另类数据适配器 (文件/占位; 非实时供应商 API)"""

from alternative_data.sentiment_csv import load_symbol_sentiment_map, sentiment_stub_status

__all__ = ["load_symbol_sentiment_map", "sentiment_stub_status"]
