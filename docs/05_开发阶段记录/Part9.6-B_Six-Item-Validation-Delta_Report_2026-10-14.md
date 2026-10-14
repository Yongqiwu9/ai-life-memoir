# Part 9.6-B — 六项补验差集结果与独立复核

## 1. 当前状态

- 日期：2026-10-14（Asia/Shanghai）。
- 基线：master @ `c25c3f85ea9f3c379001653a5109c523faa20162`，加尚未提交的获批五文件补验。
- 六项补验：相应合成、HTTP 与真实 PostgreSQL 层级验收通过；独立实现复审及 PG 证据复核均 PASS。
- 本轮仅结果文档同步及只读 Pre-Commit Audit；不运行验证、不暂存、提交或推送，不封板。
- 范围 SSOT：[六项最小补验合同](Part9.6-B_Six-Item-Validation-Delta_Contract_V1.0.md)。合同锁定 SHA-256：`4881C38C9534C7F3638DF65B4E3A0342E25BCCDEB8531B44B70A5CAEF6419738`。其 PENDING/NOT STARTED 字段保留冻结时点，不改写已独立审查的合同原文；本报告记录后续批准及实际完成状态。
- 原设计：[9.6-B 实施合同](../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。

## 2. 实际执行与证据边界

| 项目 | 实际结果 | 说明 |
| --- | --- | --- |
| 新增合成回归 | 34 passed / 247 deselected，6.13s | Service 15＋实际 ASGI 19；逐例独立内存 SQLite，FK ON |
| 完整工作区 Fast | 920 passed / 130 deselected，215.53s | 包含未提交 C3/BM-01 测试；不是远程已提交源码的测试数量 |
| CI self-check | 43 mock checks PASS | 从 Backend cwd 执行，纯 mock，不连接真实 PG |
| Ruff / format | PASS | 与 CI 相同 Backend cwd / pyproject.toml 配置 |
| PG 收集 | 45 collected | 原35＋新增10，竞争11保持；收集不等于45通过 |
| 新增 D34 真实 PG | 10 passed / 35 deselected，7.71s；0 skipped | PostgreSQL16.15/160015，本地专项只执行新增十项，不重复原竞争测试 |
| Manager migration | PASS | 现有 b196 fresh upgrade、前后 current/check 均 exit0；无新迁移 |
| 本轮远程 CI | NOT RUN | 新45/11尚未提交、推送或取得对应远程验收 |

新增合成回归引擎35/释放35，内部socketpair19/关闭19；完整Fast引擎531/释放531，内部socketpair200/关闭200；均0存活线程、0隔离拒绝、0清理/输出证据失败。PG Runner FINAL code0、alive_threads为空。

AI Service 无源码变更，复用前次58项已执行证据，本轮未重跑，不把旧结果称为本轮执行。

## 3. 六项逐项关闭口径

| 原验收项 | 新增实例 | 证据及决定 |
| --- | --- | --- |
| B18 | 2 Service | 实际 cancel 提交后 Stub timeout/非法wire；wrap真实失败完成路径核验503/502分类；取消终态200不被覆盖，同key无再次Provider调用。合成层通过 |
| B34 | 10 PG | 合法Service审批图，Core负写、实际SQLSTATE与有限(table,constraint)；SAVEPOINT回滚后完整表快照/Source保持。独立PG证据复核PASS，十项真实负例可关闭 |
| B47 | 3 Service | C2 failed_retryable同记录清空重试、精确typed snapshot重放、digest冲突保持；不把C2重试规则用于B。合成层通过 |
| B49 | 15 ASGI | 三个实际Owner DELETE入口×五Batch状态，completed count0；受控409、来源和完整父链保持，不mock409。HTTP层通过 |
| B54 | 6 Service | 787/1811精确构造diagnostic、flush/commit入口、rollback后真实scope/引用；无引用负例不误409。模拟分类层通过，不宣称真实SQLite引擎分别产生两码 |
| B57 | 4 Service＋4 ASGI | 真实命令存在但资源ID/资源/kind/终态snapshot不可核验；503unknown、无写入/正文读取/Provider重调。合成与HTTP层通过 |

总计44新增实例：Service15、ASGI19、PG10。数量不能相加推定B01–B57所有跨层或生产验收全部通过。

独立审查会话「9.6-A Review」：合同初审识别自检cwd说明冲突，最小修订后定向合同复审PASS；五文件实现及离线/ASGI证据复审PASS；本次D34十项PG和清理证据只读复核PASS。审查会话读取执行证据，未独立复跑或实时连接数据库。

## 4. D34 实际约束诊断

| 负例 | 实际 SQLSTATE | 实际 table.constraint |
| --- | --- | --- |
| current_missing_revision | 23514 | memories.ck_memories_current_pair |
| current_missing_proof | 23514 | memories.ck_memories_current_pair |
| current_cross_memory | 23503 | memories.fk_memories_current_proof |
| result_missing_memory | 23514 | revision_proposals.ck_rp_lifecycle |
| result_missing_revision | 23514 | revision_proposals.ck_rp_result_pair |
| result_cross_memory | 23503 | memories.fk_memories_current_proof |
| section_missing_revision | 23514 | memoir_sections.ck_memoir_sections_proof_pair |
| section_missing_proof | 23514 | memoir_sections.ck_memoir_sections_proof_pair |
| section_cross_revision | 23503 | memoir_sections.fk_memoir_sections_proof |
| section_cross_proof | 23503 | memoir_sections.fk_memoir_sections_proof |

result_cross_memory 实际由传入引用约束拒绝，符合已冻结有限集合；不能强制诊断表名等于被UPDATE的表。仅Section负例建立章节。未修改schema、禁用FK或制造非法基础fixture。

## 5. 资源与失败历史

- 成功 run：`b11b1369-3894-4b25-90dc-a9135ad1e1d2`；临时库 `ai_memoir_b_test_b11b136938944b2590dca9135ad1e1d2`。
- 独立受限Runner，仅本run库DML；Manager完成分配、迁移和清理。本run认证规则仅匹配新Runner，结束后恢复。
- 原生执行者均有退出结果，Manager锁进程exit0；独立只读核验库/两角色/会话/HBA错误均0，凭据载体已不存在。
- HBA恢复原始 SHA-256 `AF0FDB739B67D1A552CD82C19311B813E753D4F651A61E6B563F48B55DCA5E74`；历史库/角色OID、ACL等元数据不变；310个非敏感项目文件哈希与Git状态不变。
- 首次合成回归6失败是新增UUID/字符串表示比较及Provider计数属性问题，窄修测试后最终34通过；保留首轮日志。
- 首次PG启动run `6fcaa1eb-0bc4-4994-b9a6-7ace9be14931` 的选择gate在-k过滤前拒绝，0测试运行。其资源已独立核验清理。仅临时fixture将精确十节点检查移到collection_finish，再以全新run通过；未修改项目或削弱隔离门禁，不混用两轮证据。
- 旧v3 UNKNOWN继续保留，本轮未处理。

## 6. B38/B48 收敛与远程边界

- B38：用户确认同一旧Memory恢复正例后置C4；B阶段不因重新授权恢复旧proof，新草稿需新Revision与新审批。现有正例是另一Legacy Memory，不表述为旧Memory已恢复。
- B48：用户确认以既有18迁移场景证据＋静态约束证明收敛。合法指针/新版Section必关联B表记录，被B表非空防护涵盖；非空FK正常启用时孤儿引用不可达，约束绕过/损坏时保留防御检查。未新增非法fixture，不称每个SQL谓词独立命中。
- 已提交基线c25c3f8的[Backend CI 38554717815](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/38554717815)为completed/success：Fast608、普通PG48、B35/竞争11及迁移清理通过。该记录是此前实际远程结果，不代表当前新45/11已运行。
- CI脚本保留原35完整节点并新增10；EXPECTED、collection、JUnit、summary、mock自检均45/11。静态AST对账确认Manager/Runner/隔离/清理逻辑未变；workflow未改。
- 六项差集已完成相应层级验收；本轮不单凭差集宣布整个57项全层验证或E-01整体关闭。真实Provider、C4 Consent/Access Gate与旧Memory恢复、C6删除传播/净化/备份/第三方能力保持既有未完成边界，NOT PRODUCTION READY。

## 7. 本机原始证据索引

原始证据位于仓库外；不复制connection.json、密钥、凭据或HBA正文入库。

- [合成与实施报告](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/six-delta-20261014/implementation-report.json)
- [34项目标回归日志](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/six-delta-20261014/targeted-final.log)
- [完整Fast日志](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/six-delta-20261014/fast.log)
- [静态源码与45/11清单对账](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/six-delta-20261014/static-audit.json)
- [D34真实PG报告](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/d34-pg-run-ed108c5572c24e36ae312958e1be8402/final-report.json)
- [十项实际诊断日志](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/d34-pg-run-ed108c5572c24e36ae312958e1be8402/tests-3.log)
- [独立清理核验](/C:/Users/Administrator/.codex/visualizations/2026/10/05/01a10a3f-4e32-75c1-aebe-b864659ab21b/pg-b-specialized-20261013/d34-pg-run-ed108c5572c24e36ae312958e1be8402/cleanup-readonly-verification.json)

## 8. 下一门禁

「Git Commit Review」只读Pre-Commit Audit，精确候选五源码＋本合同和必要结果文档。README、路线图、日志仅本次B结果hunk进入候选，排除既有C3/BM-01差异；AGENTS、16项历史删除、ad、env/secret不纳入。审查通过后由用户分别批准暂存、提交、推送；新exact commit的远程45/11须实际完成后再判断后续阶段状态。
