# Quant Bot - 加密货币量化交易模拟盘

零成本的加密货币量化交易 Bot，使用 Python + SQLite，先跑模拟盘验证策略。

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

## 项目结构

```
quant-bot/
├── main.py              # 主入口
├── config.py            # 配置文件 (所有参数集中管理)
├── data_fetcher.py      # 数据获取 (真实/模拟)
├── requirements.txt     # Python 依赖
├── db/
│   └── database.py      # SQLite 数据库管理
├── strategy/
│   └── ma_cross.py      # 双均线交叉策略
├── exchange/
│   └── paper.py         # 模拟盘交易所
├── backtest/
│   └── engine.py        # 回测引擎
└── utils/
    └── logger.py        # 日志工具
```

## 策略说明

### 双均线交叉 (MA Cross)

- **金叉买入**: 快线(MA10)从下方穿越慢线(MA30)
- **死叉卖出**: 快线(MA10)从上方穿越慢线(MA30)

## 配置说明

编辑 `config.py` 调整参数:

| 参数 | 说明 | 默认值 |
|------|------|--------|
| SYMBOL | 交易对 | BTC/USDT |
| TIMEFRAME | K线周期 | 1h |
| FAST_PERIOD | 快线周期 | 10 |
| SLOW_PERIOD | 慢线周期 | 30 |
| INITIAL_BALANCE | 初始资金 | 10000 USDT |
| TRADE_AMOUNT_PCT | 每次交易比例 | 30% |
| FEE_RATE | 手续费率 | 0.1% |
| BACKTEST_DAYS | 回测天数 | 90 |

## 后续扩展

- [ ] 添加更多策略 (RSI, MACD, 布林带)
- [ ] 实盘模拟 (定时获取最新数据)
- [ ] Web 看板 (资金曲线、交易记录)
- [ ] 邮件/微信通知
- [ ] 多交易对支持
