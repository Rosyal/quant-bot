"""
量化交易 Bot - 配置文件
所有可调参数集中管理
"""
import os

# ============ 交易对配置 ============
SYMBOL = "BTC/USDT"          # 主交易对 (兼容旧逻辑)
TIMEFRAME = "1h"             # K线周期: 1m, 5m, 15m, 1h, 4h, 1d
# 多币种: sync / live / backtest-all 使用; 第一项建议与 SYMBOL 一致
SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT")

# ============ 策略参数 ============
# ma_cross | vibe | rsi_macd | bb_mean_revert | ensemble
STRATEGY = "rsi_macd"
FAST_PERIOD = 10             # 快线周期 (ma_cross)
SLOW_PERIOD = 30             # 慢线周期 (ma_cross)

# --- VIBE 参数 (偏保守、追求回测胜率时可微调 RSI 阈值) ---
VIBE_MA_FAST = 10
VIBE_MA_SLOW = 30
VIBE_MA_TREND = 50           # 收盘价需在其上方才做多
VIBE_RSI_PERIOD = 14
VIBE_RSI_BUY = 38
VIBE_RSI_SELL = 55
VIBE_BB_PERIOD = 20
VIBE_BB_STD = 2.0
# 收盘价距下轨的“触及”容差: 1.0=严格触及, >1 表示允许略高于下轨
VIBE_BB_LOWER_SLACK = 1.006
VIBE_ATR_PERIOD = 14
VIBE_ATR_MIN_PCT = 0.0003
VIBE_ATR_MAX_PCT = 0.08
VIBE_STOP_ATR_MULT = 4.0
# 趋势过滤: 常规范围价在长均线之上; 极弱 RSI 时允许略低于长均线
VIBE_TREND_MA_SOFT = 0.992
VIBE_TREND_RELAX_RSI = 36
VIBE_TREND_MA_BUFFER = 0.978
# 非止损离场需至少浮盈比例(覆盖双边手续费并减少“微利变亏”)
VIBE_MIN_EXIT_GAIN = 0.0022
# 固定止盈阈值(与布林/RSI 离场取先触发者)
VIBE_TP_PCT = 0.011

# --- RSI+MACD (趋势回踩 + 金叉; 略提高单笔仓位以改善总收益) ---
RSIMACD_FAST = 12
RSIMACD_SLOW = 26
RSIMACD_SIGNAL = 9
RSIMACD_RSI_PERIOD = 14
RSIMACD_RSI_LOW = 33
RSIMACD_RSI_HIGH = 50
# 仅「MACD 动能」入场时 RSI 上限更严, 金叉仍可用完整区间
RSIMACD_RSI_MOM_MAX = 48
RSIMACD_RSI_SELL = 66
RSIMACD_MA_TREND = 50
RSIMACD_MA_SOFT = 0.995
RSIMACD_ATR_PERIOD = 14
RSIMACD_STOP_ATR_MULT = 3.4
RSIMACD_MIN_EXIT_GAIN = 0.0022
RSIMACD_TP_PCT = 0.014
RSIMACD_TRADE_AMOUNT_PCT = 0.38  # 仅 rsi_macd 策略使用

# --- 布林带均值回归 bb_mean_revert ---
BBMR_BB_PERIOD = 20
BBMR_BB_STD = 2.0
BBMR_RSI_PERIOD = 14
BBMR_RSI_BUY = 40
BBMR_RSI_SELL = 58
BBMR_LOWER_SLACK = 1.008
BBMR_ATR_PERIOD = 14
BBMR_STOP_ATR_MULT = 3.2
BBMR_MIN_EXIT_GAIN = 0.0022
BBMR_TP_PCT = 0.012

# --- 多策略投票 ensemble (子策略名须与下方注册一致) ---
# 投票组合: 2 票通过才开仓; 子策略列表可改 (须在 ensemble._SIGNAL_REGISTRY 已注册)
ENSEMBLE_COMPONENTS = ("bb_mean_revert", "vibe", "rsi_macd")
ENSEMBLE_MIN_VOTES = 2

# ============ 账户风控 (回测层, 与策略内止损并行) ============
RISK_ENABLED = True
# 权益从峰值回撤超过该比例: 触发熔断 (禁止新开仓)
RISK_MAX_DRAWDOWN_PCT = 0.18
# 触发时是否立即市价平掉全部持仓
RISK_FORCE_FLAT_ON_DRAWDOWN = True
# 单笔最大保证金占用上限 (再与策略自带 TRADE_AMOUNT_PCT 取 min)
RISK_MAX_POSITION_PCT = 0.42

# ============ 模拟盘配置 ============
INITIAL_BALANCE = 10000.0    # 初始资金 (USDT)
TRADE_AMOUNT_PCT = 0.32      # 默认每次交易资金比例 (vibe/ma_cross)
FEE_RATE = 0.001             # 手续费率 (0.1%)

# ============ 数据库配置 ============
DB_PATH = "data/quant_bot.db"

# ============ 回测配置 ============
BACKTEST_DAYS = 90           # 回测天数
BACKTEST_START = None        # 回测起始日期 (None=自动计算)
MIN_CANDLES_FOR_BACKTEST = 80  # 满足 MA/布林/ATR 预热

# ============ 实盘信号轮询 / 通知 (仅拉行情+推送, 不下单) ============
LIVE_POLL_INTERVAL_SEC = 60
LIVE_LOOKBACK_BARS = 200
LIVE_STATE_PATH = "data/live_signal_state.json"
FEISHU_WEBHOOK_URL = ""      # 飞书自定义机器人 Webhook, 留空则不推
GENERIC_WEBHOOK_URL = ""     # 任意可接 JSON POST 的地址

# --- 企业微信「群机器人」(与个人微信不同: 消息发到企业微信群里) ---
# 在企微群 → 添加群机器人 → 复制 Webhook 地址；勿把完整地址提交到 Git。
# 优先读环境变量 (推荐): set WECOM_WEBHOOK_URL=完整链接
# 或: set WECOM_WEBHOOK_KEY=xxxxxxxx (仅 key 一段, 程序自动拼 URL)
WECOM_WEBHOOK_URL = os.environ.get("WECOM_WEBHOOK_URL", "").strip()
WECOM_WEBHOOK_KEY = os.environ.get("WECOM_WEBHOOK_KEY", "").strip()


def get_wecom_webhook_url() -> str:
    """返回企业微信群机器人完整 Webhook URL, 未配置则空串。"""
    if WECOM_WEBHOOK_URL:
        return WECOM_WEBHOOK_URL
    if WECOM_WEBHOOK_KEY:
        return (
            "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
            f"?key={WECOM_WEBHOOK_KEY}"
        )
    return ""

# ============ 报告输出 ============
REPORTS_DIR = "reports"

# ============ 日志配置 ============
LOG_LEVEL = "INFO"           # DEBUG, INFO, WARNING, ERROR
LOG_PATH = "logs/bot.log"
