# 客户交付说明（Quant Bot）

本文档用于**向最终客户说明产品定位、能力与法律边界**。交付方应确保客户在阅读并理解后再使用本软件。

---

## 1. 产品定位（能做什么）

本仓库是一套**研究与模拟工具链**，用于：

- 历史数据**回测**、多策略**对比**、**耦合/蒙特卡洛**压力观察  
- **纸面实盘**（本地模拟成交，不接交易所下单 API）  
- **信号轮询**（仅推送，默认不下单）  
- **Web 看板**（查看纸面账户状态）  
- **策略组合搜索**（`combo-search` 等，用于假设筛选，非承诺收益）

**客户可以**在充分理解风险的前提下，用上述能力做策略验证与流程演练。

---

## 2. 绝对不能对客户作出的承诺

以下内容**不得**作为销售或合同条款向客户保证：

- 「使用本软件即可盈利」「稳定赚钱」「长期保证正收益」  
- 「无风险」「保本」「等同于理财收益」  
- 「回测/模拟结果等于未来实盘表现」

**原因简述**：金融市场存在不可预测性；回测存在过拟合、幸存者偏差；软件不提供投资建议或资产管理牌照下的受托服务（视贵司法辖区而定）。

**建议话术**：本系统提供**数据与规则框架下的回测与模拟能力**；是否交易、仓位与风险由客户自行决策，盈亏由客户承担。

---

## 3. 交付方建议提供的「客户价值」（合规表述）

- **流程**：从拉数据 → 回测 → 多策略对比 → 纸面模拟 → 看板/通知的完整链路  
- **风控参数**：可在 `config.py` 与 `--profile stability` 中体现保守预设（仍非盈利保证）  
- **透明度**：策略逻辑在 `strategy/` 中可读，结果可复现（固定种子与版本）  
- **教育**：引导客户完成 `python main.py client-guide` 与本文档阅读  

---

## 4. 环境与客户操作清单

### 4.1 环境

- Python 3.9+（与交付环境一致）  
- `pip install -r requirements.txt`  
- 网络：真实行情回测需能访问交易所公开 API（如 Binance 等，取决于 ccxt 配置）

### 4.2 客户首次建议执行的命令

```bash
python main.py client-guide          # 终端内风险与命令摘要
python main.py strategies            # 查看策略列表
python main.py backtest --mock       # 无网冒烟
python main.py compare --mock --days 60
```

纸面与看板（可选）：

```bash
python main.py paper-live --once --mock --strategy ensemble_strict
python main.py web
```

---

## 5. 客户常改配置（`config.py`）

| 类别 | 项 | 说明 |
|------|-----|------|
| 品种 | `SYMBOL`, `SYMBOLS` | 主品种与多品种列表 |
| 周期 | `TIMEFRAME` | 如 `1h`, `4h` |
| 默认策略 | `STRATEGY` | 与 `python main.py strategies` 中名称一致 |
| 风控 | `RISK_*` | 回撤熔断、单笔上限 |
| 稳健预设 | 见 `runtime/presets.py` | CLI `--profile stability` |
| 通知 | 飞书/企微/Server酱/SMTP | 勿将密钥提交到 Git |
| 消息池 | `NEWS_RSS_FEEDS`、`NEWS_ASSIST_APPEND_LIVE` / `NEWS_ASSIST_APPEND_PAPER` | 需网络拉取 RSS；境内可能需代理或换源；先 `python main.py news-sync` 再通知附摘要 |
| 回测成交 | `FEE_RATE`、`SLIPPAGE_BPS`、`BACKTEST_RISK_FREE_ANNUAL` | 贴近撮合成本；报告含买入持有对比与超额；仍非实盘保证 |
| 稳健性检验 | `python main.py walk-forward` | 多样本外分段统计，**不**等价于未来可复现收益 |
| 敏感性 / 情景 | `sensitivity`、`stress-scenario`、`regime-report` | 历史假设与统计分段，**非**压力测试认证或监管模板 |
| 成交导出 | `backtest --export-trades` | CSV 便于外部分析；不含交易所对账字段 |

**消息池说明**：从配置的 RSS 抓取标题摘要，按规则打上类别/粗情绪标签并写入本地库；`live` / `paper-live` 推送可在文末附带近期摘要。**不得**向客户表述为「内幕」「必涨必跌依据」或替代自主风控——仅为信息辅助。

---

## 6. 实盘与合规

- 本仓库**默认不接交易所自动下单**；若贵方二次开发接入实盘 API，须单独评估：**交易所条款、当地证券/衍生品法规、适当性、反洗钱、客户协议与风险披露**。  
- **信号推送**（`live`）仅作信息参考，不应被描述为「跟单必赚」。

---

## 7. 机构化脚手架（与「市面机构系统」的关系）

本仓库新增模块用于**研究、演示与二次开发挂点**，**不构成**以下任一能力的等价替代：

| 能力 | 本仓库提供的内容 | **不是** |
|------|------------------|----------|
| 订单簿 / 冲击 | `execution/` 限价梯度近似、平方根冲击、VWAP 吃单 | 交易所真实 L2、撮合序、共址延迟 |
| 多资产组合优化 | `portfolio/` 静态风险平价 / 最小方差（numpy） | 动态再平衡、约束优化器、税务与杠杆账户 |
| 因子与横截面 | `factors/` 动量/波动 + 截面 z-score | 完整 Barra/Axioma、另类数据供应商、因子检验平台 |
| Barra-lite / 风格 | `factors/risk_model.py`、`factors/style_factors.py`、`factor-desk` | 行业因子、协方差稳健估计、监管资本模型 |
| 另类数据 | `alternative_data/sentiment_csv.py`、`ALT_DATA_SENTIMENT_CSV` | 实时另类数据管道、清洗与版权合规 |
| OMS / EMS | `oms/` 订单对象、多通道顺序路由、`oms-submit`、纳秒计时 | 交易所 OMS、智能拆单、共址微秒执行 |
| 实时风控与中台 | `middle_office/` 敞口/保证金/`mo-rules-check`；`approval_*` 表 | 净额清算、全产品保证金、工作流引擎、监管规则镜像 |
| 多账户与税务 | `accounts/`、`tax-export`、SQLite 划拨记录 | 银行托管、会计准则报表、纳税申报表 |
| 低延迟实盘路由 | `routing/` 统一入口、计时、审计钩子；`CCXT_LIVE_ENABLED` 默认 **关** | 微秒级链路、内核旁路、托管机房 |
| 合规与审计 | `compliance/` 单笔/时段策略；`audit_events` 表 + 可选 JSONL | 监管报送、法务签字、SOX 认证 |
| 托管与权限 | `security/` RBAC（`QUANT_BOT_ROLE`）；Web 审计接口需密钥 | HSM、多签、企业 IAM/SSO |

**客户话术建议**：上述能力为「技术脚手架与仿真」，是否用于实盘、如何满足当地法规，由客户与法律顾问自行判断；交付方不承诺通过本软件即满足任何合规或托管标准。

**相关命令**：`python main.py institutional`；另见 `oms-submit`、`exposure-report`、`mo-rules-check`、`approval-submit` / `approval-list` / `approval-resolve`、`accounts-show` / `accounts-seed` / `accounts-transfer`、`tax-export`、`factor-desk`、`alt-data-status`（`python main.py --help`）。

---

## 8. 版本与责任

- 交付时请注明 **Git 提交哈希或版本号**，便于问题追溯。  
- 因市场波动、参数误设、网络或第三方 API 导致的损失，**不属于软件缺陷保证范围**（除非另有书面合同约束）。

---

## 9. 联系与定制

（由交付方填写：支持渠道、定制范围、是否提供培训与 SLA。）
