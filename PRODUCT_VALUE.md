# 产品价值与卖点（对内 / 售前）

本文档描述 **可诚实对外陈述的能力边界**。量化软件不能替代投研结论，也不构成投资建议；**禁止**向客户承诺保本、稳赚或替代监管许可。

## 治理三层（写入 JSON/PDF/对内培训）

| 层级 | 定位 |
|------|------|
| **工具层** | 回测、walk-forward、纸面、TCA、Web/PWA 看板等 — **提高验证效率**。 |
| **证据层** | `product-brief` 证据包、多样本外章节、纸面轨迹、可选审计 — **积累可展示证据链**。 |
| **决策层** | 是否实盘、仓位、适当性与对外话术 — **须由人与合规流程决定**；软件不生成投顾结论。 |

以上结构在证据包 JSON 字段 `governance_triad` 与 `evidence_chain` 中固化，便于官网/CRM 与交付物对齐口径。

## 可售卖的「能力」而非「收益」

| 维度 | 说明 |
|------|------|
| 研究与验证 | 多策略回测、与买入持有对比、绩效与 TCA、Walk-forward、耦合测试等 |
| 数据 | 数字货币（ccxt）、A 股现货 K 线（AkShare），可本地化 |
| 运营与交付 | 纸面模拟、Web/PWA 看板、审计与审批流（仿真）、SQLite 落库 |
| 工程形态 | 可 `pip`/wheel 安装、Windows 可打 exe、配置与环境变量驱动 |

## CLI：完整证据包（推荐）

```bash
# 默认输出含治理三层 + 全样本 brief（主策略）+ multi_strategy_briefs（若指定）
python main.py product-brief --mock --json

# 多策略批量 brief（逗号分隔，与主策略去重合并）
python main.py product-brief --mock --strategies ma_cross,rsi_macd --json

# 合并 walk-forward「样本外章节」（主策略）
python main.py product-brief --mock --walk-forward --train-bars 200 --test-bars 100 --json

# 单页 PDF（需 pip install fpdf2；中文建议设 QUANT_BOT_PDF_FONT 指向 .ttf）
python main.py product-brief --mock --pdf reports/dossier.pdf

# 旧版仅单页 brief JSON（不含治理三层 / WF，与 --pdf 等互斥）
python main.py product-brief --mock --compact-json
```

JSON `schema` 字段：`quant_bot_product_dossier_v1`。

## 官网 / CRM：HTTP API（需密钥）

1. 设置环境变量：`QUANT_BOT_BRIEF_API_KEY`（与审计 API 密钥独立）。
2. 启动看板：`python main.py web`
3. 拉 JSON：

```http
GET /api/product-brief?key=<密钥>&mock=1&days=45&strategies=ma_cross,rsi_macd&walk_forward=1&train_bars=200&test_bars=100
```

4. 拉 PDF：

```http
GET /api/product-brief.pdf?key=<密钥>&mock=1&days=45
```

参数与 CLI 含义一致：`strategy`、`profile`、`mock`、`days`、`strategies`、`walk_forward`、`train_bars`、`test_bars`、`step`。

## 「赚钱能力」如何严肃表述

- 软件提供 **流程与证据链**：回测 → 样本外 → 纸面 →（可选）小资金实盘。  
- **Alpha 是否存在**只能由数据与持续验证回答；软件不自动生成合法投顾结论。  
- 对外材料须附带 `CLIENT.md` 类披露，并由具备资质的人员审阅。

## 与竞品差异化的叙述角度（示例）

- 一体化：行情、回测、风控预设、纸面、看板、机构化扩展点。  
- 可私有化：数据与审计可落本地。  
- 证据包可编程拉取（JSON/PDF），便于 CRM / 官网自动化。

---

*文档随版本迭代；以 `CLIENT.md` 与监管要求为准。*
