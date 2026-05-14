"""
报告导出 — Excel / HTML / PDF
"""
import os
from datetime import datetime
from utils.logger import get_logger

logger = get_logger("reports.exporter")


def export_excel(result: dict, output_path: str = "") -> str:
    """导出回测结果为 Excel"""
    try:
        import openpyxl
    except ImportError:
        logger.warning("openpyxl 未安装，尝试 xlsxwriter")
        try:
            import xlsxwriter
        except ImportError:
            raise RuntimeError("请安装 openpyxl 或 xlsxwriter: pip install openpyxl")

    if not output_path:
        os.makedirs("output", exist_ok=True)
        output_path = f"output/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "回测报告"

    headers = ["指标", "值"]
    rows = [
        ["策略", result.get("strategy", "")],
        ["交易对", result.get("symbol", "")],
        ["初始资金", result.get("initial_balance", 0)],
        ["最终资金", result.get("total_value", 0)],
        ["总盈亏(%)", f"{result.get('profit_pct', 0):+.2f}%"],
        ["总交易次数", result.get("total_trades", 0)],
        ["胜率(%)", f"{result.get('win_rate', 0):.2f}%"],
        ["盈亏比", result.get("profit_factor", 0)],
        ["夏普比率", result.get("sharpe_ratio", 0)],
        ["最大回撤(%)", f"{result.get('max_drawdown_pct', 0):.2f}%"],
        ["买入持有基准(%)", f"{result.get('benchmark_profit_pct', 0):+.2f}%"],
        ["超额收益α(%)", f"{result.get('alpha', 0):+.2f}%"],
    ]

    ws.append(headers)
    for row in rows:
        ws.append(row)

    # 交易明细
    if result.get("trades"):
        ws2 = wb.create_sheet("交易明细")
        ws2.append(["时间", "方向", "价格", "数量", "手续费", "盈亏", "盈亏%"])
        for t in result["trades"]:
            ws2.append([
                t.get("timestamp", ""), t.get("side", ""),
                t.get("price", 0), t.get("amount", 0),
                t.get("fee", 0), t.get("profit", 0), t.get("profit_pct", 0),
            ])

    wb.save(output_path)
    logger.info(f"Excel 报告已导出: {output_path}")
    return output_path


def export_html_report(result: dict, output_path: str = "") -> str:
    """导出回测结果为 HTML"""
    if not output_path:
        os.makedirs("output", exist_ok=True)
        output_path = f"output/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>回测报告</title>
<style>
body{{font-family:sans-serif;max-width:800px;margin:40px auto;padding:0 20px;color:#333}}
table{{border-collapse:collapse;width:100%;margin:20px 0}}
th,td{{border:1px solid #ddd;padding:8px 12px;text-align:left}}
th{{background:#4f6ef7;color:white}}
tr:nth-child(even){{background:#f5f5f5}}
h1{{color:#4f6ef7}}
</style></head><body>
<h1>回测报告</h1>
<table>
<tr><th>指标</th><th>值</th></tr>
<tr><td>策略</td><td>{result.get('strategy','')}</td></tr>
<tr><td>交易对</td><td>{result.get('symbol','')}</td></tr>
<tr><td>初始资金</td><td>{result.get('initial_balance',0):.2f}</td></tr>
<tr><td>最终资金</td><td>{result.get('total_value',0):.2f}</td></tr>
<tr><td>总盈亏</td><td>{result.get('profit_pct',0):+.2f}%</td></tr>
<tr><td>总交易次数</td><td>{result.get('total_trades',0)}</td></tr>
<tr><td>胜率</td><td>{result.get('win_rate',0):.2f}%</td></tr>
<tr><td>盈亏比</td><td>{result.get('profit_factor',0):.2f}</td></tr>
<tr><td>夏普比率</td><td>{result.get('sharpe_ratio',0):.2f}</td></tr>
<tr><td>最大回撤</td><td>{result.get('max_drawdown_pct',0):.2f}%</td></tr>
<tr><td>买入持有基准</td><td>{result.get('benchmark_profit_pct',0):+.2f}%</td></tr>
<tr><td>超额收益α</td><td>{result.get('alpha',0):+.2f}%</td></tr>
</table></body></html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"HTML 报告已导出: {output_path}")
    return output_path


# 别名
export_html = export_html_report
