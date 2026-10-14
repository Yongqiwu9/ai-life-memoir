# Part 9.6-B — 六项最小补验合同 V1.0

## 1. 状态与基线

- 日期：2026-10-14。
- Status：SCOPE FROZEN — PENDING INDEPENDENT CONTRACT REVIEW。
- Implementation：NOT AUTHORIZED / NOT STARTED。
- Git baseline：master @ c25c3f85ea9f3c379001653a5109c523faa20162。
- 本次授权：合同归档及独立只读审查；不包含测试源码修改、测试运行、数据库操作或 Git 写操作。
- 详细设计 SSOT：[9.6-B 实施合同](../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。
- 历史验证：[补验报告](Part9.6-B_Supplemental-Validation_Report_2026-10-14.md)。
- 本合同仅填补 B18、B34、B47、B49、B54、B57 的证据差集，不改变产品政策、业务状态机或审批权威。

## 2. 已确认的范围收敛

### B38

用户已确认：9.6-B 验证重新授权不自动恢复历史内容、旧审批不复活、新草稿须经新 Revision 与新审批。现有正例使用另一条 Legacy Memory，不称为同一旧 Memory 恢复通过。同一旧 Memory 的恢复正例后置 C4。本轮不新增恢复功能。

### B48

用户已确认：采用已有迁移执行证据与静态约束证明，不新增迁移或非法 fixture。

- Memory origin/current/proof 及新版 Section 的合法引用必然关联 B 表记录，被 B 表非空拒绝降级防护涵盖。
- Legacy 孤儿引用在正常启用且已验证的非空 FK 下不可达；约束失效、被绕过或数据库损坏时可能出现，保留防御检查。
- 已有 18 个迁移场景包括 Legacy 字节保留及降级拒绝后行/结构快照不变。
- `UNION ALL ... LIMIT 1` 的整体拒绝证据不表述为每个 SQL 谓词独立命中。

两项不列入本次新增测试集合；收敛不代表 C4 或损坏数据库恢复已实现。

## 3. 精确实施白名单（待批准）

| 文件 | 唯一允许的改动 |
| --- | --- |
| apps/backend/tests/test_memory_workflow.py | B18、B54、B57 的合成 Service 回归；局部必要 fixture/helper |
| apps/backend/tests/test_collaboration.py | B47 的 C2 非敏感幂等回归；局部必要 fixture/helper |
| apps/backend/tests/test_memory_workflow_api.py | B49 与 B57 的实际 ASGI 用例；局部必要 fixture/helper |
| apps/backend/tests/integration/test_memory_workflow.py | B34 十个 PostgreSQL 真实约束负例；局部必要 fixture/helper |
| scripts/ci/run_memory_workflow_postgres.py | 新增十个节点的精确 EXPECTED 清单、45 项计数及相关 mock self-check 对账 |

仅五个源码路径。不得改 conftest、workflow、runtime、Model、Schema、Service、CRUD、安全代码或 migration。不得删除、削弱原断言或 skip 原用例。若发现真实缺陷或五文件无法完成，报告 finding 并暂停相应关闭，不借测试增补授权修业务代码。

本轮文档写入仅本合同；后续结果文档同步另行明确范围。保留 AGENTS、C3/BM-01 既有修改、16 项历史删除、ad 与 ignored .env.test；不读取 ad、环境密钥或凭据载体。

## 4. 新增断言合同

### D18 — 取消提交后迟到失败（B18，2 个 Service 实例）

建议节点：`test_delta_b18_cancelled_before_late_provider_failure[failure]`，failure 为 timeout、invalid_response。

1. 复用实际 reserve / cancel / 失败完成调用链，Provider 为离线 Stub；Stub 内先通过现有 cancel Service 提交取消，再主动抛 TimeoutError 或返回确实违反 wire 合同的结果。迟到错误进入 start 的分类 except 与 _finish_failure，不要求成功 _finalize 被调用。
2. 使用 wraps 真实 _finish_failure 的 spy，精确核验 timeout=(AI_PROVIDER_TIMEOUT,503)、invalid_response=(AI_INVALID_RESPONSE,502)；不以永不消费的错误替身代替。
3. 原调用返回 cancelled metadata、200；失败完成不得把已取消 Batch 改成 failed。
4. cancelled 的 version、finished_at、discard_reason 以及提取命令终态保持取消提交时值；无 failure_code、Candidate、Revision、Proposal 或 Memory 新增。
5. 同 key 再调用返回原取消终态、200；Provider 总调用一次；Source 原文不变。

不增加 deadline、真实延迟或超时中断保证。已有 pending 状态 TimeoutError=503、非法结果=502 与部分写入 rollback 证据继续保留。

### D34 — PostgreSQL 约束负写（B34，10 个 PG 实例）

建议单一参数化节点：`test_delta_b34_postgres_reference_constraints[violation]`。

先使用合成图及现有合法审批 Service 建立两套已批准 Memory/Revision/proof；需要 Section 时通过现有 Memoir Service 创建合法章节。提交有效 fixture 后使用 Core SQL 单次负写绕过 ORM 写保护，验证真实数据库约束。不得删除约束、禁用 FK、制造无效基础 fixture 或依赖 superuser Runner。

| violation | 负写 | 预期 SQLSTATE |
| --- | --- | --- |
| current_missing_revision | current_revision_id=NULL，保留非空 proof | 23514 |
| current_missing_proof | current_approval_proposal_id=NULL，保留非空 revision | 23514 |
| current_cross_memory | 把另一 Memory 的完整 revision/proof 对挂到本 Memory | 23503 |
| result_missing_memory | 已批准 Candidate Proposal 的 result_memory_id=NULL，仅保留 result revision | 23514 |
| result_missing_revision | 已批准 Candidate Proposal 的 result_memory_revision_id=NULL，仅保留 result memory | 23514 |
| result_cross_memory | 已批准 Candidate Proposal 使用真实存在、但与 result revision 不匹配的另一 Memory ID | 23503 |
| section_missing_revision | approved_revision_snapshot 的 memory_revision_id=NULL，保留 proof | 23514 |
| section_missing_proof | approved_revision_snapshot 的 approval_proposal_id=NULL，保留 revision | 23514 |
| section_cross_revision | Section 改用另一 Memory 的真实 Revision，保留原 memory/proof | 23503 |
| section_cross_proof | Section 改用另一 Memory 的真实 proof，保留原 memory/revision | 23503 |

断言 actual SQLSTATE、真实 table_name 与属于本负写相关约束的精确 constraint_name 集合。多个同时违反的约束允许精确有限集合，不假定 PostgreSQL 检查顺序；集合从现有迁移静态定义核对，不接受任意 FK/CHECK。若列出的负写实际存在另一语义约束影响分类，独立审查先澄清，不临时扩大集合掩盖结果。

每例在 SAVEPOINT 内触发并 rollback；之后重新读数据库，比较目标行、current、proof、result、Section、Source 与行数均未变化，确认 Session 可继续查询。十个实例分别使用自己的合成业务图，不共享可变 fixture。

已有 XOR、subject、input FK 及 11 项竞争证据不作为新增差集重复执行；本地只选择上述十个新增节点。现有远程专项 job 后续正常执行完整清单，见 §5。

### D47 — C2 failed_retryable 与旧重放（B47，3 个 Service 实例）

建议节点前缀：`test_delta_b47_c2_`。

1. `failed_retryable_resets_same_record`：构造合法 C2 operation 的 failed_retryable 命令，保留合成旧 resource/response/completed_at；调用原 C2 begin。返回同一 record、replayed=False、processing；清空 resource_kind/id、response_status/body、completed_at，actor/operation/key/digest 不变；无第二命令。随后通过 C2 complete 写合法 typed snapshot，再 begin 重放，精确返回原 status/snapshot。
2. `completed_replays_snapshot`：合法 C2 completed 记录同 digest 重放返回同记录与 replayed=True；字段、计数、快照不变，不要求 B HMAC key 或 B metadata。
3. `retryable_digest_conflict_preserves_record`：failed_retryable 同 key 不同 digest 返回 409 IDEMPOTENCY_CONFLICT；所有既有字段不重置，无新记录。

使用 C2 已注册 operation 与已允许的非敏感 snapshot 类型；不把 arbitrary operation 或 raw dict 当合法快照。不改变 C2 实现，也不将 C2 可重试规则应用到 B。

### D49 — 旧 DELETE 全 Batch 状态 HTTP 矩阵（B49，15 个 ASGI 实例）

建议节点：`test_delta_b49_old_delete_all_batch_states[target-state]`。

- target 为 interview/member/family；state 为 pending/completed/failed/discarded/cancelled，3×5=15。
- 每例独立内存 SQLite，PRAGMA foreign_keys=ON；使用满足 lifecycle CHECK 的 Batch，零 Candidate；completed 的 candidate_count=0。
- 使用现有真实 app/client、Owner JWT、现有三个 DELETE URL；不传新增 Idempotency-Key 或 expected_version。
- 响应必须 409 RESOURCE_IN_USE，使用标准安全错误结构，无正文/SQL/约束名/引用计数泄漏。
- 响应后重新读取：Family、Member、Interview、Session、Source、Batch 完整保留，原文与 Batch 生命周期字段不变，Candidate/Revision/Proposal/Memory 无新增。
- 不 monkeypatch metadata 预检为 True，不 mock Router/Service 返回409；不依赖 AI/HMAC/许可 adapter 才能拒绝删除。

使用正常 DEBUG 模式即可；已有两种 DEBUG 实际 ASGI 脱敏证据继续复用，不为该15项再乘 DEBUG 参数。

### D54 — SQLite 双码精确分类（B54，6 个 Service 实例）

建议节点：`test_delta_b54_sqlite_reference_classification[code-phase]` 四个正例，code=787/1811，phase=flush/commit；以及 `test_delta_b54_sqlite_fk_shape_without_references[code]` 两个负例。

- 构造 sqlite3.IntegrityError，精确 `sqlite_errorcode` 及原文 `FOREIGN KEY constraint failed`，包装 SQLAlchemy IntegrityError；经实际删除 Service guard 的 flush/commit 异常入口。
- 四个正例有真实合成引用图；首轮预检为 stale false，rollback 后重新查实际 Owner scope 和引用。必须 rollback 在重新授权/引用核验之前发生，得到受控409 RESOURCE_IN_USE，资源/原文保留；不得仅 mock 最终错误。
- 两个负例：同精确码与形态但回滚后查不到受保护引用，不能被认作409；断言原 IntegrityError 继续传播，且先完成 rollback。已有无关 trigger 文本及 PG 未知 FK 等负例不重复。
- 分类异常为受控构造的 diagnostic，不声称真实 SQLite 引擎分别产生787和1811。历史实际引擎 FK 用例保留，并报告其实际码；禁止把 `in (787,1811)` 改称两码都实际命中。
- 本次不重新扩展 ASGI DEBUG 矩阵；其现有真实执行证据独立引用。

### D57 — 命令存在但结局不可核验（B57，4 Service＋4 ASGI 实例）

建议节点：`test_delta_b57_unverifiable_existing_command[case]`、`test_delta_b57_unverifiable_existing_command_http[case]`。

四个 case：missing_resource_id、missing_resource、unsupported_resource_kind、malformed_terminal_snapshot。

- 使用当前 actor、合法 URL member、已注册 B operation 及真实存在的 Command 行。Command resource_id 无业务 FK 的分支可直接合法构造，不删除实际业务行来制造缺口。
- missing_resource 为未分配的 UUID；unsupported_resource_kind 为现有 String 列允许但解析不支持的值；malformed_terminal_snapshot 必须关联真实同 scope 资源并确实进入终态解析分支。
- 均返回503 COMMAND_OUTCOME_UNKNOWN，不推断已回滚、不自动重执行。
- Service 用 spy/禁止调用验证无 begin/get-or-create/commit/flush、业务写入、正文读取或 Provider 调用；查询前后完整合成表快照一致。
- ASGI 用真实 GET status 路径和 Owner JWT 验证固定安全503及 metadata 白名单；Provider调用数0，业务行不变，无自动修复。HTTP请求Session正常关闭/rollback不等同业务写入，不禁止fixture正常清理。
- 有效资源属于另一 URL member 时仍为404；不把该情况改为503。本轮不重复其他actor隔离用例，禁止为判断存在性枚举其他actor命令。

## 5. 数量与 CI 接线

新增固定实例数：D18=2、D34=10、D47=3、D49=15、D54=6、D57=8，总计44。参数化 ID 与闭环证据逐例对账；新增数不代替执行结果。

- 原 PG35＋D34十项=PG45；原 CONCURRENT11 保持不变。新增负例不标记并发。
- CI 脚本 EXPECTED、collection gate、JUnit expected counts、summary 和 mock self-check 必须一致更新为45/11；禁止只改总数、接受任意节点、删原35或允许skip。
- workflow 与原集成入口排除 B 文件保持不变。无需新增 job、容器或通用启动平台。
- 原历史35/11证据保留为对应commit的历史事实；新45不得在实际运行前写成通过。

## 6. 分阶段验收与授权

### 阶段一：独立合同审查（本轮授权）

「9.6-A Review」只读核对五文件范围、44实例、SQLSTATE/约束可达性、HTTP路径、fixture能力及CI45/11接线。报告明确 finding、严重度与是否阻塞实施；禁止修改源码、测试运行、PG/Docker/migration/Git写入。可将报告发送回「总任务架构设计确认」。

审查通过且文本哈希锁定后，提交用户批准精确五文件实施范围。审查PASS不自动批准实施或真实执行；存在 finding 时先修订合同再定向复审。

### 阶段二：测试源码与合成验证（后续待批准）

只修改 §3 五文件；首先新增合成 Service/C2/HTTP 节点定向执行，继而一次全量 Fast 回归与相关 Ruff/format，CI脚本 `--self-check` 仅mock。AI Service无源码改动，复用已核验来源哈希的58项证据，不重复运行。

候选命令（授权后由现有受限执行方式运行，不能裸命令绕过保护）：

```text
python -m pytest tests/test_memory_workflow.py tests/test_collaboration.py tests/test_memory_workflow_api.py -k test_delta_ -q
python -m pytest -m "not integration" -q
python ../../scripts/ci/run_memory_workflow_postgres.py --self-check
```

三个命令均在 apps/backend 工作目录；CI mock self-check 的缺失 GITHUB_WORKSPACE 负例不能从仓库根运行，以免 Path("") 恰好等于 ROOT 而改变该负例的前提。不修改 context gate。Fast须使用现有逐例独立内存SQLite/FK fixture，合成配置，默认真实处理关闭，禁止dotenv/秘密读取、外网、真实Provider、真实数据库及项目写入；允许事件循环必需内部loopback socketpair。临时目录由同一执行身份预检。统计Service与实际HTTP分别的结果；完整Fast包含未提交C3用例时必须明确，不能替代已提交commit CI证据。保存进程退出、engine/socketpair/线程清理与工作区只读对账。

未额外授权前，PG仅改测试源码、收集/静态核对节点，不连接数据库或执行migration。

### 阶段三：独立实现复审及专项 PG（后续待批准）

先独立只读复审新增断言与离线证据。通过后申请一次专项真实 PostgreSQL16.15资源授权，沿用[现有容器复用合同](Part9.6-B_PostgreSQL16.15_Existing-Container-Reuse_Validation-Contract_V1.0.md)，由 Manager 分配全新唯一DB/owner/受限Runner；临时Runner认证规则改变须符合专项授权。不得复用已清理run或历史库。

运行前 SELECT version/server_version_num 必须确认16.15/160015。Manager迁移到现有b196，不新增迁移；运行前后 current/check。Runner仅运行新增D34十个实例：

```text
python -m pytest -m integration tests/integration/test_memory_workflow.py -k test_delta_b34_postgres_reference_constraints -q
```

真实分配信息/多连接门禁保持原状，不为非并发负例伪造授权。十项均必须PASS、0skip，保留每个actualSQLSTATE/约束证据。Manager确认相关进程退出后精确清理新DB/roles、本run认证规则，核验DB/role不存在、认证配置恢复、历史资源未变。退出、身份或清理不确定则STOP/保留，不能报告整体闭环成功。

### 阶段四：结果文档与 Git（均需后续授权）

按44实例差集及层级汇总，明确合成diagnostic/实际SQLite/HTTP/真实PG/mockCI。只有对应实际执行及独立审查满足后才能关闭六项。文档同步另列精确路径；再由「Git Commit Review」审计并建立精确暂存白名单。暂存、commit、push分别待批准。Push后检查exact commit远程Backend CI及完整PG45/11结果与清理，不能引用旧commit35项代替。

## 7. 关闭标准与停止条件

- 六项各自满足 §4 断言、实际执行证据及独立复审；未执行部分标NOT RUN/NOT VERIFIED，不能预判通过。
- 无业务语义、C2重试规则、权限隔离、HMAC、删除传播或Consent改变；runtime/migration/workflow变更均0。
- 不修改C3/BM-01既有工作、不清旧UNKNOWN探针、不扩建启动平台。
- 不声称真实Provider、C4授权恢复、C6清除、备份/第三方删除或生产验收已完成；本合同不封板、不开始下一阶段。
- 发现断言不可达、既有fixture无法符合范围、实际结果与合同不一致、白名单外改动或资源不确定，停止该项并报告；不得改预期只求绿灯。

## 8. 批准栏

| 项目 | 状态 |
| --- | --- |
| 六项补验范围 | SCOPE FROZEN |
| 独立合同审查 | PENDING |
| 五文件测试增补与合成/HTTP执行 | PENDING USER APPROVAL |
| 真实PostgreSQL专项执行 | PENDING SEPARATE RESOURCE APPROVAL |
| 结果文档同步、暂存、commit、push | NOT AUTHORIZED |

范围冻结不等于实施已批准，也不等于验收完成。
