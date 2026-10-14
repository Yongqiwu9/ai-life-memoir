# Part 9.6-B — 补充验收与文档同步记录

## 1. 当前结论与基线

- 日期：2026-10-14（Asia/Shanghai）。
- Git 基线：`master @ 0099016455f21cd32bed3bbe1c3d24a313ab140d`，加已批准、尚未提交的补验测试与 CI 清单变更。
- 五文件独立源码复审：会话「9.6-A Review」给出 **PASS WITH FINDINGS**，无阻塞 PG 专项执行的缺陷；唯一新增 Low `SUP-IR-01` 后经窄范围修复、目标回归和定向只读复审 **CLOSED / PASS**。
- 本文归档已执行证据，不新增实施、测试、数据库或 Git 操作授权，不宣布整个 9.6-B 封板或生产就绪。
- 详细业务合同仍为 [9.6-B Implementation Contract](../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。[早期闭环独立复核](Part9.6-B_Validation-Closure_Independent-Review_2026-10-14.md)保留原文和原验证时点；本文记录其后的补验差集。

## 2. 验证结果与时间边界

| 验证 | 实际结果 | 范围与限制 |
| --- | --- | --- |
| 完整工作区 Fast | **886 passed / 120 deselected，179.28s** | 合成内存 SQLite，包含新增 109 项，其中 23 项为实际 HTTP/ASGI 用例；120 项 integration 未执行。工作区含既有未提交 C3/BM-01 内容，不等于已提交源码的远程测试数量 |
| 独立 AI Service | **58 passed，0.56s** | 既有 `services/ai-service/tests/test_memory_extraction.py`，离线 Mock/合同验证；未连接真实 Provider |
| PostgreSQL 16.15 专项 | **35 passed，3.69s；0 skipped；11 项竞争测试全部通过** | 真实 SQL 版本 `16.15 / 160015`；现有容器内唯一新建临时库、独立 owner 与受限 Runner；非全量 integration |
| Alembic 专项 | **PASS** | Manager fresh upgrade 到 `b196f0d47a21`；测试前、后 `current/check` 均通过；未修改迁移源码 |
| 专项 CI 脚本纯模拟自检 | **43 项通过** | 按实际 CI 工作目录 `apps/backend` 执行；纯模拟不证明真实 Linux/PG 生命周期。仓库根目录存在既有 `IncompleteContextAccepted` 自检限制，本轮未改门禁 |
| 五文件 Ruff / Format / Diff | **PASS** | 测试增补与 CI 严格清单范围；不扩展为全仓静态审计结论 |
| SUP-IR-01 目标回归 | **3 passed，0.55s** | 完整 Fast 之后，仅收紧 terminal replay 断言，精确要求 `failed=503`、`discarded=409`、`cancelled=200`；未再次运行完整 Fast 或 PG |

Fast 的 497 个内存数据库引擎全部释放，181 个内部 socketpair 全部关闭，存活线程为 0；SUP-IR-01 目标回归的 4 个引擎全部释放，socketpair 与存活线程均为 0。

**不得将上述数量相加推断 57 项业务验收全部通过。** 886 与 58 是 SUP-IR-01 修复前的验证快照；最终修复后的新增执行证据仅为 3 项目标回归及定向只读复审。本次文档同步未重跑测试。

## 3. 补验覆盖与独立复审

- 新增离线参数化实例 109 项：workflow 77、memoir 9、HTTP 23；另增 PG 7 项。因此新增源码实例总数为 116，109 不含新增 PG。
- 旧 PG 28 项完整保留；新增 Provider 无事务与父链/Batch/Command 锁释放探针 1 项、既有 Memory 两审批竞争 1 项、Candidate/Memory ordinal 竞争 2 项、预检后新增引用与 Interview/FamilyMember/Family 删除竞争 3 项，合计 35 项。
- 竞争清单为原有 5 项加新增 6 项，共 11 项；Provider 锁释放探针独立包含在 35 项内，不重复计入 11 项。
- B20：固定 caller 物理连接，第二 Runner 使用不同 backend PID，对父链及 pending Batch/Command 使用 NOWAIT 锁，验证 Provider 调用期间事务与预留锁已释放。
- B32/B33：独立 Runner 连接与不同 PID；在服务自身 target 锁处用 `pg_blocking_pids` 验证实际阻塞，核验批准/过期结果、ordinal、version、current Revision 与审批 proof。
- B52：真实第二连接在引用预检与 DELETE 之间提交新 Batch；检查实际 `23503`、受保护 `(table_name, constraint_name)`、安全 `409` 和来源/父行保留。这是 immediate FK / DML 兜底，不声称制造了 commit-time FK 或实际锁等待；commit 分类另有合成故障注入证据。
- 独立复审确认：权限拒绝先于正文/Provider；重放不重新生成；重跑不覆盖人工修订/已批准 Memory；HMAC 绑定、非法状态/版本、用途依赖、Memoir 旧 proof、删除保护及 HTTP 脱敏具有实质断言，未弱化既有门禁。
- SUP-IR-01：仅把 `status in {200,409,503}` 改为逐状态精确断言；零 Provider 调用、禁止正文读取和数据行数不变断言完整保留。定向复审核验前后文件哈希一致，未复跑测试，不把静态审查等同执行证据。

## 4. 真实 PG 分配与清理证据

| 项目 | 已核验结果 |
| --- | --- |
| 本次 run UUID | `074c4869-3c51-4e91-8b10-c33ec4922db7` |
| 复用容器 | `ai-memoir-c3-pg16`；ID `1e4f6a0a344c9eee9de80847b66e096fc5bfa76a2854faa485b7bb81ce80db73` |
| 实际版本 / cluster system_identifier | `160015` / `7694724439064498215` |
| 唯一临时库 | `ai_memoir_b_test_074c48693c514e918b10c33ec4922db7`，已核验不存在 |
| 本次 owner / Runner | `b_owner_074c48693c514e918b10c33ec4922db7` / `b_runner_074c48693c514e918b10c33ec4922db7`，均已核验不存在 |
| Runner 隔离 | 非管理员；实际拒绝连接历史库、postgres、template1；只在本次库执行业务用例，不获得迁移/清理权限 |
| 退出与会话 | 测试进程 exit 0，存活测试线程 0；所有记录进程均确认退出，Manager 锁进程 exit 0；临时库/角色相关会话 0 |
| HBA 恢复 | 原始字节哈希恢复为 `af0fdb739b67d1a552cd82c19311b813e753d4f651a61e6b563f48b55dca5e74`，reload 后规则错误 0 |
| 清理后只读复验 | 临时库 0、角色 0、会话 0；临时连接凭据载体已删除；历史数据库 OID/owner/ACL、历史角色元数据不变 |
| 项目保护 | 308 个既有受保护文件哈希不变，Git 状态不变，暂存区为空；16 项历史删除、untracked `ad`、ignored `.env.test` 保持 |

未使用历史库承载合成业务数据，未新建容器、未 force drop、未按前缀清理、未终止不明进程。本次没有新遗留资源；旧 v3 探针的历史退出仍为 **UNKNOWN**，不能用本次清理证明旧资源已退出或已清理。

## 5. 本地与远程证据分离

已保存的 [Backend CI run 38512280122](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/38512280122)对应 **exact commit `0099016455f21cd32bed3bbe1c3d24a313ab140d`**，backend 和 B PostgreSQL 两个 job 均 `completed / success`；其中 Fast 499、普通 PG integration 48、B 专项 PG 28／竞争 5、迁移与清理通过。该提交满足 **B-PC-01 原 CI 接线关闭条件**。

当前补验后的 **35／11 严格清单尚未提交、推送或取得对应远程 CI**；不能把旧 run 的 28／5 或本机 35／11 写成新清单的 remote PASS。CI 脚本仍为专用 CI 入口；本机实际执行复用获授权的现有容器专项 Manager/Runner 脚本，不激活通用 BM-01 provisioning。

## 6. 保留限制与下一门禁

- `E-01` 的 B32/B33/B52 指定 PG 竞争证据差集已补齐，但不按测试数量整体关闭 E-01。57 项逐项对账、尚未单独覆盖的 Legacy 孤儿/版本化 Section 等回退分支仍需保留证据限制；既有 Legacy 18 项是历史脚本场景，不是本次新执行或新增 pytest 数量。
- 真实 AI Provider **NOT IMPLEMENTED**，不接入真实个人资料、录音/STT、RAG 或生产环境。
- C4 Consent / Source Binding / Access Gate 与 C6 Deletion / Ledger / Outbox / Sanitization / 备份和第三方删除传播 **未因本次验证完成**；完整生产流程仍未实现/未证明。合成 receipt 的恢复用例只证明新版本/新审批门禁，不证明 C4 同一旧 Memory 的恢复流程。
- Owner-only 内容边界不变；不能用 Owner 审批替代 Speaker 同意、撤回或删除权。生产 retention、真实 Provider 清除能力等既有未决事项不由本次测试决定。
- `DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY`。未直接封板、未开始下一阶段。
- 下一步为只读 Pre-Commit Audit：基于当前真实文档/测试差异重新列精确 whitelist；README、路线图与日志仍混有历史 C3/BM-01 hunks，不能整文件自动视为本次批准提交。暂存、提交、推送仍须分别授权；之后核对新 exact commit 的远程 CI。

## 7. 原始证据索引

原始日志保留在本机外部目录，不复制密钥、连接配置或历史私有材料到仓库；本文提供可随文档审阅的摘要。以下为本次核对的既有证据，不代表文档同步重新执行验证。

- 合成/Fast/AI：[验证报告](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/b-supplement-20261014/final-report.json)、[Fast 日志](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/b-supplement-20261014/fast-confirmed.log)、[AI Service 日志](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/b-supplement-20261014/ai-final.log)。该报告中的 PG NOT RUN 是当时快照，随后真实执行见下一条。
- 真实 PG：[最终报告](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/b-pg-supplement-run-3c65112601a542c7bb451a344067edb7/final-report.json)、[35 项日志](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/b-pg-supplement-run-3c65112601a542c7bb451a344067edb7/tests-3.log)、[清理只读复验](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/b-pg-supplement-run-3c65112601a542c7bb451a344067edb7/cleanup-readonly-verification.json)。该报告中的 Low 为修复前快照，关闭见下一条。
- SUP-IR-01：[目标回归与定向复审闭环](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/sup-ir-01-closure-20261014/closure-evidence.json)。
- 已提交基线的远程 CI：[本机归档报告](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/local-fast-remediation-20261014/remote-ci-38512280122/Push-Remote-CI-Report.md)。

Fast 和 PG 执行时 `test_memory_workflow.py` SHA-256 为 `2ECE44AE235FE9C750FB33C1C5A0953557E737A732CC5432E7BC15AC793814DF`；SUP-IR-01 断言收紧后为 `E1C72D24774DA2F5C9E6F97A8856A7060B713D770F21D87F067D380165B70D3F`，只对应 3 项新目标回归及定向复审。PG 专项用例与 CI 清单未因该修复变化。
