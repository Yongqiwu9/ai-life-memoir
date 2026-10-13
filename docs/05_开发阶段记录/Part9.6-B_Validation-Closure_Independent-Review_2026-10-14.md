# Part 9.6-B — Validation Closure Independent Review

来源：会话「9.6-A Review」，2026-10-14。以下保存独立复核原文；不表示提交批准或整个 57 项验收完成。

**《Part 9.6-B 验证闭环独立只读复核报告》**
审查日期：2026-10-14

**结论：PASS WITH FINDINGS。** B-IR-01～04 修复成立，现有 HTTP、PostgreSQL、Legacy 专项证据支持其声明范围。未发现新的业务阻塞缺陷；**不能据此宣布合同 57 项全部验收完成或生产可用。**

本轮未修改文件、运行验证、连接数据库、读取 `.env`／`connection.json`，也未执行 Git 写操作。

### 1. 源码一致性

[闭环审查 manifest](C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/closure-review-manifest.json)列出的 **42 个文件，初始和结束哈希均匹配，零差异**。

### 2. 四项修复决定

| Finding | 决定 | 核验依据 |
|---|---|---|
| B-IR-01：Provider 身份未经校验 | **CLOSED** | Owner／能力门禁后、原文读取前验证离线 Provider；Batch 记录实际身份，调用同一对象；重放不解析 Provider。[校验入口](C:/Users/Administrator/Documents/ChatGPT/ai-life-memoir/apps/backend/app/services/ai_memory_client.py:19) |
| B-IR-02：Memoir 快照缺少 proof／Revision 锁 | **CLOSED** | 按 Command → UUID 排序的 Memory → Proposal → Revision 加锁，锁内重新核验再复制、单次提交；真实 PG 用例覆盖 proof／body 清除的两种提交顺序。[锁顺序](C:/Users/Administrator/Documents/ChatGPT/ai-life-memoir/apps/backend/app/services/memoir.py:71) |
| B-IR-03：HTTP fixture 未覆盖 Router 实际依赖 | **CLOSED** | 覆盖 Router 绑定的 `get_memory_client`，使用计数 Mock，并保存／恢复 overrides；成功提取和默认关闭用例已实际通过。[fixture](C:/Users/Administrator/Documents/ChatGPT/ai-life-memoir/apps/backend/tests/test_memory_workflow_api.py:131) |
| B-IR-04：测试误读 Memoir 响应字段 | **CLOSED** | 测试读取 `memoir_id`，继续核验章节、精确 Revision／proof 和正文；未为迁就测试修改 API 合同。[成功流程](C:/Users/Administrator/Documents/ChatGPT/ai-life-memoir/apps/backend/tests/test_memory_workflow_api.py:227) |

### 3. 实际验证证据

| 验证 | 已核验结果 | 支持范围 |
|---|---|---|
| HTTP／ASGI | **15 passed，3.67s**；原生退出码 0、管道 EOF；15 个 fixture engine 全部释放，存活线程 0 | 合成能力注入、提取重放、人工审批、精确 Memoir、权限与安全错误响应 |
| PostgreSQL 16.15 | **28 passed，2.68s**；前后 `current` 为 `b196f0d47a21`，`check` 无新升级操作 | FK／CHECK／结构约束、引用保护、精确晋升及指定双连接竞争 |
| Legacy／downgrade | **18 个场景记录 PASS**；最终 `current/check` 通过 | 合成旧数据保留、安全回退、拒绝不安全回退且不改变快照 |

HTTP 的[退出记录](C:/Users/Administrator/AppData/Local/Temp/memoir-http-authorized-7ad7bd81d59b4d4199567e26bf778c19/exit.json)与日志一致；实际执行脚本哈希也与身份记录匹配。

PG 的 28 项包含 **5 个双连接参数化用例**：Candidate 两提案竞争 1 项，以及 Memoir 与 proof／body 清除的两种顺序 4 项。后者断言了不同 backend PID 和实际锁等待，属于真实 PG 竞争证据，不能视为普通 Mock。[双连接用例](C:/Users/Administrator/Documents/ChatGPT/ai-life-memoir/apps/backend/tests/integration/test_memory_workflow.py:491)

Legacy 脚本比较旧行字段，包含 ID、正文、FK 字段和时间；检查新增工作流表为空、Legacy 标识／零计数／NULL proof；拒绝回退时比较完整行与结构快照。[迁移断言](C:/Users/Administrator/AppData/Local/Temp/memoir-pg-legacy-892f1daa80584aa4a0d63784204f6548/migration_cases.py:35)

### 4. Findings 与证据限制

**E-01 — Medium，覆盖证据限制，非已确认业务缺陷。**

合同 57 项是业务场景清单；HTTP 15、PG 28、Legacy 18 是不同测试集合，存在重叠，不能相加推断全部覆盖。尤其：

- B52 的“预检后并发新增引用”未见对应的真实 PG 竞争用例；已有 SQLite 补充验证不能替代它。
- B32 的既有 Memory 两提案批准竞争、B33 的 ordinal 并发，不能由 Candidate 晋升或 Memoir 清除竞争代替。
- Legacy 的 18 项包含最终 `current/check`，并非 18 个独立 pytest 测试。
- 合成 Policy／Integrity 验证不证明真实 Consent、C6 清除、备份或第三方删除传播。

因此，应按具体场景标注已验证范围，保留未覆盖项；无需因此否定四项修复或已完成的专项结果。

### 5. 失败历史与清理

已读取成功及失败 run 的公共 manifest。记录显示各相关隔离库、角色已不存在，HBA 已恢复，锁进程退出码为 0。

失败历史未混入成功结果：早期 PG 执行曾有 **26 failed／2 passed**；Legacy 初次执行存在缺少 `is_active` 的错误。后续使用独立 run 完成修正后的验证。清理结论来自记录和对应脚本断言，**本轮未实时查询服务器复验**。

旧 v3 的历史退出继续 **UNKNOWN**；新验证结果不替代旧退出证据。

### 6. 后续边界

可以同步文档，准确记录四项修复关闭及上述专项通过范围。仍应保留 57 项逐项覆盖缺口、真实能力接入与生产验收限制。

本轮未修改文档、未开始 Pre-Commit Audit，也不宣布 BM-01 CLOSED。

## 原报告补充说明

已按各实际 run 目录中的入口副本核对：PG 28 项与 Legacy 专项使用各自的 pg_child.py，未用最新临时脚本替代历史入口。Legacy 18 项是脚本验收场景，不是新增 pytest 用例。真实 Legacy 孤儿、版本化 Section 等未单独覆盖的回退分支仍属证据限制。原结论 PASS WITH FINDINGS 保持；不宣称全部 57 项完成，旧 v3 继续 UNKNOWN。
