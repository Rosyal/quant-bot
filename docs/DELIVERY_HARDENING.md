# 交付硬化指南（适当性、密钥、灾备、对账、网关、监管占位）

> 本文档补充 `CLIENT.md`，供**交付方 / 合规 / 运维**在上线前核对。不构成法律意见。

---

## 一、适当性与风险披露（软件能做的）

1. **交付动作**  
   - 随安装包提供 `CLIENT.md` 与本文档。  
   - 要求最终用户在界面或合同中确认已阅读「不保本、不保证收益、历史不代表未来」。  
2. **产品内入口**  
   - `python main.py client-guide`  
   - `python main.py product-brief` / `ops-readiness`（证据链 JSON）。  
3. **Web 看板**  
   - 页眉已增加简短风险提示（见 `web/templates/index.html`）。  
   - 默认启用 Flask `after_request` 安全头（`X-Content-Type-Options`、`X-Frame-Options`、基础 CSP 等）；调试可设环境变量 `QUANT_BOT_WEB_SECURITY_HEADERS=0` 关闭（见 `config.WEB_SECURITY_HEADERS_ENABLED`）。  

**须由贵司完成**：适当性评估问卷、客户分类、合同条款、销售话术合规审查。

---

## 二、权限与密钥管理（软件能做的）

1. **环境变量**  
   - 复制 `.env.example` 为 `.env`（勿提交 Git）。  
   - 所有 Webhook、API Key、SMTP 密码**只走环境变量或 KMS 注入**，不写进 `config.py`。  
2. **自检**  
   - `python main.py security-check`：弱口令/占位符粗检。  
3. **访问控制**  
   - `/api/audit`、`/api/product-brief` 等已要求 `?key=` 与独立环境变量。  
   - 生产建议：反向代理 + mTLS 或 IP 白名单 + WAF。  

**须由贵司完成**：KMS/Vault、密钥轮换制度、人员离职回收、渗透测试报告。

---

## 三、灾备（软件能做的）

1. **数据库冷备份**  
   - `python scripts/db_backup.py`  
   - 或 `python scripts/db_backup.py --dest-dir D:\backups\quant`  
2. **恢复**  
   - 停止应用 → 将备份 `.db` 复制回 `config.DB_PATH` 指定路径 → 启动。  
3. **建议**  
   - 每日定时任务执行备份；异地副本（对象存储/磁带）由运维配置。  

**须由贵司完成**：RPO/RTO 指标、演练记录、SQLite 以外的集群方案（若需要）。

---

## 四、对账（软件能做的）

- `python main.py reconcile`：汇总 `oms_orders` / `oms_executions` / `fund_transfers` / 审计抽样，输出 JSON 与**差异提示**（启发式，非会计凭证）。  

**须由贵司完成**：与券商/银行对账单勾稽、财务入账规则、差异调账流程。

---

## 五、实盘网关（软件能做的）

- 目录 `broker/` + `GATEWAY.md`：**接口与责任边界说明**（占位）。  
- 代码层真网关须按贵司选定厂商二次开发。  

**须由贵司完成**：接入审批、联调、仿真→小流量→全量。

---

## 六、监管报送占位（软件能做的）

- `python main.py regulatory-export --out reports/audit_export.csv [--hash-actors]`  
- 导出 SQLite `audit_events` 为 CSV，可选对 `actor` 做 SHA256 短哈希（内部脱敏）。  

**须由贵司完成**：报送义务认定、字段映射、法定格式、报送通道与留痕年限。

---

## 七、渗透测试（软件不能替代）

本仓库**不提供**自动化渗透或漏洞认证。交付清单建议：

- [ ] 依赖 `pip audit` / Snyk / 商业渗透服务  
- [ ] Web 仅内网或 HTTPS + 强鉴权  
- [ ] 关闭生产 `Flask debug`  

---

## 八、命令速查

| 命令 | 用途 |
|------|------|
| `python main.py security-check` | 环境与密钥粗检 |
| `python scripts/db_backup.py` | 冷备份 DB |
| `python main.py reconcile` | 对账摘要 JSON |
| `python main.py regulatory-export --out ...` | 审计 CSV 导出 |
| `python main.py ops-readiness` | 运营就绪总览 |

---

*修订日期随仓库版本迭代。*
