# Quant Bot - 加密货币量化交易模拟盘

零成本的加密货币量化交易 Bot，使用 Python + SQLite，支持多策略回测、纸面模拟、Web 看板与通知。**不承诺任何投资收益**；向客户交付前请务必阅读并随附 [`CLIENT.md`](CLIENT.md)。

## 面向客户 / 交付

- **客户说明与法律边界**：见 [`CLIENT.md`](CLIENT.md)（风险披露、禁止承诺话术、部署清单）。  
- 终端快速摘要：`python main.py client-guide`  
- 保守风控预设：`python main.py backtest --profile stability --mock`

## 快速开始

### 1. 安装依赖

```bash
cd quant-bot
pip install -r requirements.txt
```

### 2. 运行回测 (模拟数据, 无需网络)

```bash
python main.py backtest --mock
```

### 3. 运行回测 (真实数据, 需要网络)

```bash
python main.py backtest
```

### 4. 查看交易状态

```bash
python main.py status
```

## 项目结构（摘要）

| 路径 | 说明 |
|------|------|
| `main.py` | CLI 入口（回测、对比、耦合、排名、纸面、Web 等） |
| `config.py` | 全局参数 |
| `strategy/` | 多策略与投票组合 |
| `backtest/` | 回测引擎与绩效指标 |
| `exchange/` | 纸面账户 / 模拟撮合 |
| `runtime/` | live、paper-live、coupled-test、combo-search、presets |
| `web/` | Flask 看板 |
| `notifications/` | Webhook / 邮件 / Server酱 |
| `news/` | 消息池（RSS → 分类入库；`news-sync` / `news-list`；看板 `/api/news`） |
| `execution/` | 订单簿近似、平方根冲击、VWAP 阶梯（仿真） |
| `portfolio/` | 多资产风险平价 / 最小方差 |
| `factors/` | 横截面动量、波动、z-score |
| `routing/` | 执行路由、延迟记录（`router-dry-run`） |
| `compliance/` | 交易前策略校验、审计写入 |
| `security/` | RBAC（`QUANT_BOT_ROLE`） |
| `oms/` | OMS 订单对象、多通道 EMS（故障切换 + `latency_ns`） |
| `middle_office/` | 净敞口、保证金、规则引擎、与审批表衔接 |
| `accounts/` | 多账户账本划拨、`tax-export` 辅助 CSV |
| `alternative_data/` | 另类数据 CSV 适配（如情绪分数） |
| `factors/risk_model.py` | Barra-lite 协方差（单市场因子 + 特异方差） |
| `CLIENT.md` | **客户交付与风险披露**（含机构化脚手架边界 §7） |

完整子命令：`python main.py --help`。

## 策略说明

运行 `python main.py strategies` 查看全部策略（含 `ensemble`、`ensemble_strict`、`combo-search` 组合搜索等）。经典示例：双均线金叉/死叉见 `strategy/ma_cross.py`。

## 配置说明

编辑 `config.py`。客户常改项见 [`CLIENT.md`](CLIENT.md) 第 5 节。

| 参数 | 说明 | 默认值 |
|------|------|--------|
| SYMBOL | 交易对 | BTC/USDT |
| TIMEFRAME | K线周期 | 1h |
| STRATEGY | 默认策略名 | rsi_macd |
| INITIAL_BALANCE | 初始资金 | 10000 USDT |
| BACKTEST_DAYS | 回测天数 | 90 |

## 已具备能力（扩展项）

- [x] 多策略（RSI / MACD / 布林 / 投票 / 组合搜索等）  
- [x] 纸面定时模拟 `paper-live`、Web 看板 `web`  
- [x] 飞书 / 企微 / Server酱 / SMTP 通知  
- [x] 多交易对 `SYMBOLS`、`backtest-all`  
- [x] 稳健预设 `--profile stability`（[`runtime/presets.py`](runtime/presets.py)）
- [x] 消息池：`NEWS_RSS_FEEDS` + `python main.py news-sync`，通知可附摘要（`NEWS_ASSIST_APPEND_*`）；外网 RSS 在部分网络环境需代理或可访问源

消息池为**关键词规则分类**，仅供阅读参考，**不构成投资建议**。详见 [`CLIENT.md`](CLIENT.md)。

- **成交模型**：`FEE_RATE` + `SLIPPAGE_BPS`（回测与 `PaperExchange` / 纸面账户一致）；报告含**买入持有基准**、超额收益、累计手续费。  
- **扩展指标**：Ulcer、Omega；夏普使用 `BACKTEST_RISK_FREE_ANNUAL`。  
- **Walk-forward**：`python main.py walk-forward --mock`（滚动样本外，抗过拟合参考）。
- **扩展绩效 / TCA**：信息比率(vs 买入持有)、最长回撤期 K 线、低于峰值占比、最大连亏；成交名义、费用 bps、换手代理；半 Kelly 提示（回测报告内）。
- **研究与情景**：`sensitivity`（单参数扫描）、`regime-report`（波动率 regime 占比）、`stress-scenario`（最深回撤点起权益冲击）；`backtest --export-trades PATH` 导出成交 CSV。
- **技术指标库**：`strategy/technical/base.py`（ADX、**Stochastic（入参为 candles 列表）**、Williams %R、OBV），并由 `strategy/indicators.py` 统一导出。
- **Web 热力图数据**：`GET /api/sensitivity-grid?key=...`（`QUANT_BOT_SENSITIVITY_API_KEY` 或复用 `QUANT_BOT_AUDIT_API_KEY`；参数见 `web/app.py`）。
- **回测摘要 Excel**：`reports/xlsx_export.py` → `write_backtest_summary_xlsx`（依赖 `openpyxl`）。

与头部商业平台相比仍可能缺少：实盘订单管理系统 (OMS)、实时风控引擎、多账户资金划拨、另类数据与因子平台、合规工作流与审批链等——需按业务单独采购或二次开发。
