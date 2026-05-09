"""
量化交易 Bot - 配置文件
所有可调参数集中管理

客户交付时请一并提供仓库内 CLIENT.md，并说明：本软件不承诺投资收益。
客户常改: SYMBOL / TIMEFRAME / STRATEGY / RISK_* / SYMBOLS；稳健 CLI: --profile stability
"""
from __future__ import annotations

import os

# ============ 市场与交易标的 ============
# crypto: 数字货币 (ccxt); cn_a: A股现货行情 (AkShare, 6 位代码)
MARKET_MODE = "crypto"
if os.environ.get("QUANT_BOT_MARKET"):
    MARKET_MODE = (os.environ["QUANT_BOT_MARKET"].strip().lower() or "crypto")
if MARKET_MODE not in ("crypto", "cn_a"):
    MARKET_MODE = "crypto"
# A股复权: qfq 前复权 | hfq 后复权 | "" 不复权
CN_A_ADJUST = os.environ.get("QUANT_BOT_CN_ADJUST", "qfq").strip() or "qfq"

# 主标的: 数字货币如 BTC/USDT; A股如 600519
SYMBOL = "BTC/USDT"
TIMEFRAME = "1h"             # K线周期: 1m, 5m, 15m, 1h, 4h, 1d (A股常用 1d)
# 多标的: sync / live / backtest-all; A股示例 ("600519", "000001")
SYMBOLS = ("BTC/USDT", "ETH/USDT", "SOL/USDT")

# ============ 策略参数 ============
# ma_cross | ema_cross | triple_ma | donchian | roc_mom | vibe | rsi_macd | ...
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

# --- 纯 RSI rsi ---
RSI_ONLY_PERIOD = 14
RSI_ONLY_OVERSOLD = 32
RSI_ONLY_OVERBOUGHT = 68
RSI_ONLY_USE_MA = True
RSI_ONLY_MA_PERIOD = 50

# --- 纯 MACD macd ---
MACD_ONLY_FAST = 12
MACD_ONLY_SLOW = 26
MACD_ONLY_SIGNAL = 9

# --- 纯布林带 bollinger ---
BB_ONLY_PERIOD = 20
BB_ONLY_STD = 2.0
BB_ONLY_LOWER_SLACK = 1.008
BB_ONLY_TP_TOUCH_UPPER = True
BB_ONLY_ATR_PERIOD = 14
BB_ONLY_STOP_MULT = 3.2

# --- 三均线 triple_ma ---
TRIPLE_MA_FAST = 5
TRIPLE_MA_MID = 15
TRIPLE_MA_SLOW = 35

# --- 双 EMA 交叉 ema_cross ---
EMA_CROSS_FAST = 12
EMA_CROSS_SLOW = 26

# --- 唐奇安突破 donchian ---
DONCHIAN_PERIOD = 20

# --- ROC 动量 roc_mom (N 根收盘涨跌幅) ---
ROC_MOM_PERIOD = 10
ROC_MOM_BUY = 0.015    # >= 1.5% 做多
ROC_MOM_SELL = -0.01   # <= -1.0% 平仓

# --- rank-models 综合分权重 (和不必为 1, 仅相对排序) ---
RANK_COMPOSITE_W_PROFIT = 0.35
RANK_COMPOSITE_W_SHARPE = 0.30
RANK_COMPOSITE_W_MDD = 0.25
RANK_COMPOSITE_W_WINROUND = 0.10

# 耦合测试/排名报告中「盈利轮占比」对照阈值 (0~1)。仅历史统计口径, 非实盘或未来收益保证。
TARGET_COUPLED_WIN_ROUND_RATIO = 0.65

# --- 多策略投票 ensemble (子策略须在 strategy/ensemble_core.SIGNAL_REGISTRY) ---
# 投票组合: 2 票通过才开仓
ENSEMBLE_COMPONENTS = ("bb_mean_revert", "vibe", "rsi_macd")
ENSEMBLE_MIN_VOTES = 2

# --- 高门槛投票 ensemble_strict (更稀疏信号, 常提高耦合盈利轮占比、降低交易次数) ---
ENSEMBLE_STRICT_COMPONENTS = (
    "bb_mean_revert",
    "vibe",
    "rsi_macd",
    "ema_cross",
    "macd",
)
# 5 中取 3: 比 ensemble(2/3) 更严, 仍常有成交; 若需更少信号可改为 4
ENSEMBLE_STRICT_MIN_VOTES = 3

# 稳健型仓位/风控覆盖见 runtime/presets.py（CLI: --profile stability）。不保证盈利。

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
FEE_RATE = 0.001             # 手续费率 (单边, 如 0.1%)
# 成交价滑点 (基点): 买在参考价上加、卖在参考价上减, 1 bps = 0.01%
SLIPPAGE_BPS = 5.0

# ============ 回测风险指标 ============
# 年化夏普/索提诺使用的无风险利率 (年化小数, 如 0.03 = 3%)
BACKTEST_RISK_FREE_ANNUAL = 0.03

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

# --- 纸面实盘模拟 (定时拉 K 线 → 信号 → 模拟成交, 持久化 JSON) ---
PAPER_LIVE_STATE_PATH = "data/paper_live_state.json"
PAPER_LIVE_INTERVAL_SEC = 60
PAPER_LIVE_LOOKBACK_BARS = 200
# 单笔买入占用「当前总权益」的比例 (受可用 USDT 限制)
PAPER_TRADE_AMOUNT_PCT = 0.28

# --- Server酱 Turbo (微信服务号): https://sct.ftqq.com/  SendKey ---
SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "").strip()

# --- SMTP 邮件 ---
SMTP_ENABLED = False
SMTP_HOST = ""
SMTP_PORT = 587
SMTP_USER = ""
SMTP_PASSWORD = ""
SMTP_FROM = ""
SMTP_TO = ""
SMTP_USE_TLS = True  # 587 + STARTTLS; 若用 465 SSL 可设 False 并在部分客户端改用 SSL(见 email_smtp)

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

# ============ 消息池 (RSS → 分类入库 → 通知/看板辅助) ============
# 非投资建议; 关键词规则见 news/classifier.py, 可后续接 LLM。
# 示例: ("https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss")
# 留空则不同步; 境内访问外网 RSS 可能需代理或换可访问源
NEWS_RSS_FEEDS: tuple[str, ...] = ()
NEWS_FETCH_TIMEOUT_SEC = 22
NEWS_MAX_ITEMS_PER_FEED = 25
NEWS_DIGEST_HOURS = 48
NEWS_DIGEST_MAX_ITEMS = 4
# live / paper-live 推送是否附带最近消息摘要 (需先 news-sync 且库内有数据)
NEWS_ASSIST_APPEND_LIVE = True
NEWS_ASSIST_APPEND_PAPER = True

# ============ 报告输出 ============
REPORTS_DIR = "reports"

# ============ 日志配置 ============
LOG_LEVEL = "INFO"           # DEBUG, INFO, WARNING, ERROR
LOG_PATH = "logs/bot.log"

# ============ 机构化脚手架 (仿真/扩展点; 非持牌合规、非银行托管) ============
# 市场冲击: 参考深度 (美元) 与平方根律强度 (见 execution/order_book_impact.py)
ORDERBOOK_SYNTH_DEPTH_USD = 5_000_000.0
ORDERBOOK_IMPACT_GAMMA = 0.55
# 执行路由后端: noop | paper_stub | ccxt_live (真下单须 CCXT_LIVE_ENABLED 且自行实现)
ROUTER_BACKEND = "paper_stub"
ROUTER_LATENCY_WARN_MS = 250.0
CCXT_LIVE_ENABLED = False
# 交易前策略: 单笔上限 (USDT); UTC 时段 None=不限制, (9,17)=9<=h<17
COMPLIANCE_MAX_ORDER_USDT = 100_000.0
COMPLIANCE_TRADING_HOURS_UTC: tuple[int, int] | None = None
# 审计双写: 环境变量 QUANT_BOT_AUDIT_JSONL 可覆盖; 设为空字符串则仅写 DB
_AUDIT_ENV = os.environ.get("QUANT_BOT_AUDIT_JSONL", "data/audit.jsonl")
AUDIT_JSONL_PATH = _AUDIT_ENV.strip()
# RBAC 默认角色; 可用环境变量 QUANT_BOT_ROLE=admin|trader|readonly 覆盖
SECURITY_DEFAULT_ROLE = "trader"

# ============ OMS / 中台 / 多账户 (扩展点) ============
# 保证金率 (简化期货式); 仅 middle_office 演示
MARGIN_INITIAL_RATE = 0.10
MARGIN_MAINTENANCE_RATE = 0.05
# 超过该名义的 OMS 演示单需先走审批 (可用 CLI bypass, 见 main --help)
APPROVAL_REQUIRED_ABOVE_USDT = 250_000.0
# 另类数据示例 CSV (列: symbol,sentiment_score[,asof_ts])
ALT_DATA_SENTIMENT_CSV = os.environ.get("QUANT_BOT_ALT_SENTIMENT_CSV", "").strip()

# --- 上线增强: OMS 订单表幂等、实时风控、审批 SLA ---
OMS_IDEMPOTENCY_ENABLED = True
RISK_REALTIME_RULES_ENABLED = False
# 毛敞口+本笔名义 / 权益 上限; 0 表示不启用该规则
RISK_MAX_LEVERAGE_GROSS_TO_EQUITY = 0.0
# 从峰值回撤比例 (0~1), 由 desk PipelineContext.meta 传入 current_drawdown_pct 时生效
RISK_BLOCK_NEW_BUY_IF_DRAWDOWN_PCT = None  # 例: 0.25
# 当日亏损占权益比例 (负数), 由 meta 传入 daily_loss_pct 时生效
RISK_DAILY_LOSS_LIMIT_PCT = None  # 例: 0.05 表示亏损超过 5% 拦截
# approval-expire 将早于此刻的 pending 标为 expired (小时)
APPROVAL_SLA_EXPIRE_HOURS = 168

# ============ 全链路编排 (desk/pipeline) ============
# paper-live 是否在成交前跑完整链路 (中台规则 + 路由审计 + EMS); 默认关
FULL_CHAIN_PAPER_LIVE = False
# 纸面场景下是否跳过「超名义需审批」(仍执行规则与路由); 默认 True 便于连续模拟
FULL_CHAIN_PAPER_BYPASS_APPROVAL = True

# ============ EMS 模拟撮合 / 延迟画像 / 净额 ============
# 模型化交易所侧延迟分布: colo | retail | cross_region (见 oms/latency_profile.py)
_EMS_LAT = os.environ.get("QUANT_BOT_EMS_LATENCY", "").strip().lower()
EMS_LATENCY_PROFILE = _EMS_LAT or "retail"
# 是否先走 sim_slow 再进 matching_sim (演示 failover); 设 0 可直达撮合
_EMS_FF = os.environ.get("QUANT_BOT_EMS_FAILOVER_FIRST", "1").strip().lower()
EMS_FAILOVER_SIM_SLOW_FIRST = _EMS_FF not in ("0", "false", "no", "off")
# 是否写入 oms_executions; 是否滚动 clearing_net_positions
_EMS_P = os.environ.get("QUANT_BOT_EMS_PERSIST", "1").strip().lower()
EMS_PERSIST_EXECUTIONS = _EMS_P not in ("0", "false", "no", "off")
_EMS_N = os.environ.get("QUANT_BOT_EMS_NETTING", "1").strip().lower()
EMS_APPLY_NETTING = _EMS_N not in ("0", "false", "no", "off")
# matching_engine 限价簿形状 (仿真)
MATCHING_HALF_SPREAD_BPS = 2.0
MATCHING_LOB_LEVELS = 8
MATCHING_TICK_BPS = 3.0

# ============ Web 安全响应头 (Flask after_request; 见 web/app.py) ============
# 环境变量 QUANT_BOT_WEB_SECURITY_HEADERS=0 可关闭 (极少数内嵌 iframe 调试场景)
_WSH = os.environ.get("QUANT_BOT_WEB_SECURITY_HEADERS", "1").strip().lower()
WEB_SECURITY_HEADERS_ENABLED = _WSH not in ("0", "false", "no", "off")
