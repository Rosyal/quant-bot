"""
量化交易 Bot - 配置文件
所有可调参数集中管理
"""

# ============ 交易对配置 ============
SYMBOLS = ["BTC/USDT"]       # 交易对列表 (支持多个)
SYMBOL = "BTC/USDT"          # 默认交易对 (兼容旧代码)
TIMEFRAME = "1h"             # K线周期: 1m, 5m, 15m, 1h, 4h, 1d

# ============ 策略参数 ============
STRATEGY = "ma_cross"        # 策略名称
FAST_PERIOD = 10             # 快线周期
SLOW_PERIOD = 30             # 慢线周期

# ============ 模拟盘配置 ============
INITIAL_BALANCE = 10000.0    # 初始资金 (USDT)
TRADE_AMOUNT_PCT = 0.3       # 每次交易使用资金比例 (30%)
FEE_RATE = 0.001             # 手续费率 (0.1%)

# ============ 风控配置 ============
RISK_STOP_LOSS = 5.0         # 止损百分比
RISK_TAKE_PROFIT = 15.0      # 止盈百分比
RISK_TRAILING_STOP = 0.0     # 移动止损 (0=关闭)
RISK_MAX_DAILY_TRADES = 0    # 每日最大交易次数 (0=不限)
RISK_MAX_DAILY_LOSS = 10.0   # 每日最大亏损百分比
RISK_MAX_CONSECUTIVE_LOSSES = 0  # 连亏暂停次数 (0=不限)

# ============ 数据库配置 ============
DB_PATH = "data/quant_bot.db"

# ============ 回测配置 ============
BACKTEST_DAYS = 90           # 回测天数
BACKTEST_START = None        # 回测起始日期 (None=自动计算)

# ============ 蒙特卡洛配置 ============
MC_SIMULATIONS = 10000       # 模拟次数 (越多越精确, 越慢)
MC_TRADES_PER_SIM = None     # 每次模拟交易次数 (None=使用历史实际次数)
MC_CONFIDENCE = 95           # 置信区间 (%)

# ============ 通知配置 ============
# Telegram: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
# 飞书: FEISHU_WEBHOOK_URL
# Server酱: SERVERCHAN_SENDKEY
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
FEISHU_WEBHOOK_URL = ""
SERVERCHAN_SENDKEY = ""

# ============ Web 配置 ============
WEB_HOST = "0.0.0.0"
WEB_PORT = 8080

# ============ KMS 加密配置 ============
KMS_MODE = "local"              # local | aws
AWS_REGION = "us-east-1"
AWS_KMS_KEY_ID = ""
KMS_LOCAL_KEY_PATH = "data/.keys/master.key"
KMS_KEY_ROTATION_DAYS = 90

# ============ WebSocket 配置 ============
WS_ENABLED = False              # 启用 WebSocket 数据源
WS_EXCHANGES = ["binance"]      # WebSocket 交易所
WS_LATENCY_THRESHOLD_MS = 100.0 # 延迟告警阈值

# ============ AkShare 配置 ============
AKSHARE_CACHE_SIZE = 200        # LRU 缓存大小
AKSHARE_DEFAULT_TTL = 300.0     # 默认 TTL (秒)
AKSHARE_WARMUP = True           # 启动时预热

# ============ 延迟监控 ============
LATENCY_ALERT_THRESHOLD_MS = 200.0  # 全链路延迟告警阈值

# ============ 日志配置 ============
LOG_LEVEL = "INFO"           # DEBUG, INFO, WARNING, ERROR
LOG_PATH = "logs/bot.log"
