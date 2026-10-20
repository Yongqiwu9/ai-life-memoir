# Part 9.6-C2 — 最小补验对账与文档收尾

- 日期：2026-10-20（Asia/Shanghai）。
- 结论：**LOCAL MINIMAL SUPPLEMENT PASS / CLEANUP CONFIRMED**。
- 阶段状态：**NOT SEALED**。补验及定向复审通过；最新源码的完整回归、D01–D73总对账、exact C2远程CI与Git闭环仍待完成。
- 基线：`master @ c8824b3c2c1d7c9ae6d633461787431166cd7a07` 加已授权工作区，不是新提交或远程CI结论。
- 详细记录：[补验证据JSON](Part9.6-C2_Minimal-Supplement-Evidence_2026-10-20.json)。

## 1. 本次归档边界

本次为Documentation Only：核对既有文件、会话审查意见、JUnit、执行及清理回执，新增本报告和脱敏证据JSON，必要同步README、路线图、开发日志。没有在本次文档任务中运行测试、HTTP、PostgreSQL、Docker或迁移；没有修改业务、测试、迁移、workflow、AGENTS或Git暂存区。

原[专项对账报告](Part9.6-C2_Specialist-Validation-Reconciliation_Report_2026-10-20.md)及[17／13证据](Part9.6-C2_Specialist-Validation-Evidence_2026-10-20.json)保持原文。其run `eb00aa2b-d934-421b-817f-def5a55f8b24`、迁移4／运行17／竞争13是旧轮次，不替换成27／16，也不与新轮次相加。

本轮实施依据为会话中批准的最小补验合同V1.1；本报告只记录已批准范围及证据，不代替[原实施合同V0.4](../04_AI设计/Part9.6-C2_Session-Text-Integration_Implementation-Contract_Draft_V0.4.md)，不新增产品决策，不为会话文本虚构文件哈希。原验证合同保留冻结时的17／13规划与NOT RUN历史。

## 2. 授权范围与历史

补验实施仅涉及三个项目文件及一个现有外部PG脚本：

1. `apps/backend/tests/test_dialogue.py`：S01–S09合成离线补验。
2. `apps/backend/tests/integration/test_dialogue.py`：P01五例、P02两例、P03三例；原17个实例保留。
3. `scripts/ci/run_dialogue_postgres.py`：固定节点、竞争子集、数量断言及相应mock自检维护。
4. 外部 `Part9.6-C2_Specialist-Source_20261017/run_c2_pg_validation.py`：相同固定节点和数量维护；不修改Manager分配、权限、HBA、超时或清理语义。

V1.1合同定向复审关闭了B-SCR-01（补齐已提交协调器／queued子命令边界）和B-SCR-02（补齐end真实抢占父子命令）。这属于合同静态范围关闭，不是当时已运行PG。未新增业务、迁移、HTTP测试或通用启动平台。

## 3. 离线补验对账

以下函数均位于[合成离线测试](../../apps/backend/tests/test_dialogue.py)。采用既有隔离bootstrap、逐例独立内存SQLite和纯C1 JSON测试替身；不连接真实Provider。

| 补验 | 代码／测试入口 | 已核对内容 |
| --- | --- | --- |
| S01 | `test_split_merge_exact_and_extra_leaf_rejected` | ready／active／retired分区精确重建；缺失、额外及孤儿敏感叶拒绝；合法问题历史保留 |
| S02 | `test_source_metadata_failure_precedes_sensitive_select` | restricted／unlinked／缺失binding在正文和敏感checkpoint读取前拒绝；缺失binding通过读取边界注入，不破坏FK |
| S03 | `test_context_body_fingerprint_change_rejects_without_rpc` | user／assistant正文指纹改变需授权读取后检测；检测失败不进一步调用AI，不虚称零正文读取 |
| S04 | `test_restart_context_preserves_summary_label_and_frozen_started_history` | 保留五类label；补充interrupted历史恢复；快照、顺序、引用与quote相等；已存started不随后来的完成/暂停改写 |
| S05 | `test_old_writers_cannot_bypass_dialogue_profile` | 旧text、transcript→Message、旧Agent入口拒绝；不继续来源查找、原文写入或AI调用 |
| S06 | `test_logical_clock_restart_and_stale_version`、`test_pure_transition_explicit_retry_preserves_event`、`test_old_silence_cycle_does_not_generate_after_new_activity` | 重启后逻辑时间不倒退，显式重放复用冻结事件；普通旧版本拒绝；新的human turn建立周期，旧静默命令不生成 |
| S07 | `test_old_completion_cannot_mutate_new_response`、`test_rotated_key_replay_requires_original_key_and_exact_payload` | 旧completion不覆盖新response；旧key仍在时精确重放；丢失旧key／改载荷拒绝，不重调Provider |
| S08 | `test_command_readback_is_metadata_only_without_repair` | missing／foreign actor／wrong profile／terminal／corrupt body对账；仅metadata SELECT，无修复、正文读取或Provider重调；end保留原文但未消费queued输入 |
| S09 | `test_child_key_collision_never_adopts_client_command`、`test_unchanged_context_has_no_refresh_or_revision_increment`、`test_two_manual_questions_without_new_text_refresh_once`及原idle测试 | 确定性child key碰撞不认领客户端命令；未变化不刷新；变化只刷新一次且revision精确加一；复用原idle零调用证据 |

实际执行记录：`unit-final.xml` **65 PASS**；末轮 `unit-delta-final.xml` **2 PASS**。其中一个节点重复，合计**66个不同节点**，不能写为67个不同用例。两组均无failure/error/skipped。

这些离线结果发生在P03两处Session生命周期修复之前，不能改记为修复后重跑；末次修复只涉及PG文件，并由后续真实PG新轮次验证。旧 `unit-first.xml` 和 `old-cycle.xml` 失败记录保留，分别记录新增造数/约束问题及将typing误当新周期的测试假设；后续修正不改写旧结果。

CI脚本在workflow指定的`apps/backend`工作目录完成47项纯mock检查；相关文件Ruff/format通过，不代表全仓lint或最新完整Fast/AI Service回归。仓库根目录自检的`IncompleteContextAccepted`来自未修改的工作目录回退行为，作为既有限制保留，未静默修复或定级为本轮新增业务漏洞。

## 4. 独立实现审查与SUP-IR-01关闭

独立审查人：`/root/supplement_implementation_review`。本节归档会话报告摘要；不声称存在独立报告文件及其哈希。

| 轮次 | 结论 | 范围 |
| --- | --- | --- |
| 初次独立实现复审 | FAIL；SUP-IR-01 Medium | 新增P03两个`with Session`未登记强引用、UNKNOWN时仍自动close；属于测试资源生命周期问题，不是已确认的业务权限绕过或数据破坏 |
| 用户批准窄修复 | 仅PG测试文件两处生命周期块 | Session创建后立即登记到`pg.guard.resources`；finally先`guard.check()`，UNKNOWN抛错并跳过close；不使用会误判存活线程的`guard.finish()`／`guard.session()` |
| 原审查人定向复审 | PASS；SUP-IR-01 CLOSED — STATIC SCOPE | 逆向还原两块后精确匹配旧哈希；等待、join、线程结果、UNKNOWN保留和业务断言不变；另三文件哈希不变 |

PG测试文件修复前SHA256：`0a629ee55c624896fc7ecf98884b8d07e9ea8d89d6052983a4a809dffa47a4d1`。

修复及定向复审后的SHA256：`6126c6929e4850122830d8f7afefcb58f3f8493099a43bc20d476aa31c1e0ec6`，与本次PG执行输入一致。

审查人仅只读核对，没有运行测试、HTTP、PG、Docker或迁移。相似历史写法未扩大到本轮修复，不能据本次关闭推断所有历史资源路径已审计。

## 5. PostgreSQL 16.15最新实际执行

- Run UUID：`651797b3-a319-44d9-ac7a-5bef75d88b83`。
- 证据目录：外部 `Part9.6-C2_Specialist-Source_20261017/run-2cf0dc4647cf4e23879173616c164f5e`。
- PostgreSQL：16.15，`server_version_num=160015`；集群`7694724439064498215`，复用既有容器，未启停或新建容器。
- 临时库：`ai_memoir_dialogue_ci_test_651797b3a31944d9ac7a5bef75d88b83`，OID71956；本次Owner OID71954、Runner OID71955。
- 精确head：`c296a4e8d102`，父版本`b196f0d47a21`。
- 本次仅一次分配、一次完整执行，不自动重跑或复用旧库。Manager迁移与低权限Runner分离，HBA仅增加本次精确规则；未改历史库ACL。

| 项目 | 实际结果 |
| --- | --- |
| Fresh upgrade／current／check | PASS |
| Manager迁移 | 4／4 PASS：Legacy升级、marker回退拒绝、旧结构回退再升级、metadata一致 |
| Runner运行 | 27／27 PASS，0 failure/error/skipped，精确节点集合匹配 |
| 其中竞争 | 16／16 PASS，是27项的子集，不相加 |
| Post-integration current／check | PASS |
| 退出与回执 | Manager exit0；lock_exit0；34份测试/迁移/后检回执确认，56个控制进程EXITED且EOF确认 |
| 清理 | CLEANED，独立核验库/角色名称及OID不存在、会话0、本次Runner HBA规则0、HBA语法错误0 |

原17项逐项重跑通过；其中13项仍是原竞争子集。新增10项如下，逐节点JUnit及回执哈希见证据JSON：

| 类别 | 精确节点 | 竞争 | 结果 |
| --- | --- | --- | --- |
| P01 | `test_coordinator_recovery_boundaries[coordinator_queued]` | 否 | PASS |
| P01 | `test_coordinator_recovery_boundaries[child_preparing]` | 否 | PASS |
| P01 | `test_coordinator_recovery_boundaries[child_completed]` | 否 | PASS |
| P01 | `test_coordinator_recovery_boundaries[parent_preparing]` | 否 | PASS |
| P01 | `test_coordinator_recovery_boundaries[parent_committed_reply_lost]` | 否 | PASS |
| P02 | `test_saved_source_recovery[preempted_preparing]` | 否 | PASS |
| P02 | `test_saved_source_recovery[committed_reply_lost]` | 否 | PASS |
| P03 | `test_stale_coordinator_reply[new_coordinator]` | 是 | PASS |
| P03 | `test_stale_coordinator_reply[new_source]` | 是 | PASS |
| P03 | `test_stale_coordinator_reply[end_preempts_parent_child]` | 是 | PASS |

P01/P02通过已知提交边界的合成异常和独立Session读回验证恢复，不杀进程、不切断真实网络/数据库；不宣称已验证所有真实进程崩溃或驱动断连。纯RPC前后未发布结果的等价持久化边界按已批准合同合并，不重复计数。P03以独立连接和同步窗口验证新协调器、新来源、end对旧父子结果的屏障。

## 6. 清理与执行输入完整性

Manager确认所有相关执行者退出后，按本次名称/OID/marker核验并普通DROP新库，再删除本次角色。未使用FORCE、任意kill或终止其他会话。历史数据库及管理角色元数据核验不变，旧UNKNOWN资源未触碰。

执行结束后的独立只读核验确认：database_remaining=0、roles_remaining=0、sessions_remaining=0、runner_hba_rules_remaining=0、hba_errors=0。HBA原文与恢复后哈希一致：`af0fdb739b67d1a552cd82c19311b813e753d4f651a61e6b563f48b55dca5e74`。

本次执行锁361项全部匹配，SHA256：`d4f88d4f635e18d9071de44dc6b189250605daa764958167f54b4d81a5dae7ed`。执行前只更新经核验的四个补验文件和三份先前已同步入口文档；旧锁有备份，七条old/new哈希有单独审计。证据JSON保存运行时输入快照和74项证据文件哈希，不保存密码、token、连接URL或HBA正文。

文档同步后的README、路线图、日志会与该历史执行锁产生三项文档差异；不刷新旧执行快照或冒称重跑。未来执行须在相应授权下重新锁定当前输入。

## 7. D55与完整验收的边界

D55按批准边界采用已有marker实际回退拒绝证据与静态约束证明：五张新表均在EXISTS防护内，State10／Turn15个新增字段均有非空防护，downgrade先锁定/检查再DDL。父约束覆盖的指针/引用状态不以禁用FK或非法孤儿fixture重造。不新增迁移，不声称每个不可能分支都被单独实际执行。

本轮S01–S09和P01–P03通过，不自动将D01–D73全部标PASS。仍待：

1. 最新源码的完整Fast／AI Service回归；此次只归档已有定向离线和专项PG结果。
2. 完整D01–D73代码、测试、执行及静态约束证明总对账的审查接受。
3. exact新C2 commit的Backend／Dialogue相关远程CI；本地47项mock自检不替代真实Linux／PG／远程结果。
4. Pre-Commit Audit、精确暂存、提交和推送的分别授权与Git闭环。

HTTP仍仅引用2026-10-19合成Backend48／AI Service6 PASS，本轮未重复；不是生产JWT、真实Consent或真实业务端到端验收。

真实Provider/费用能力、语音/STT/TTS、真实个人资料、日记/资料集与多来源功能、C3激活/C4 Consent/C6删除、生产、BM-01及旧UNKNOWN限制继续保留。**不得由本报告宣布C2 Completed／Sealed或启动下一功能阶段。**

## 8. 文档收尾状态

本轮仅新增本报告/证据JSON并同步三个项目入口，原合同、审查、失败记录、17／13报告和执行目录保留。未运行任何测试或数据库，未暂存、提交或推送；暂存区为空，16项历史模板删除仍unstaged，`ad`保持untracked且未读取，`.env.test`保持ignored且未读取。既有AGENTS、C3/BM-01及其他工作区内容保持。

下一步是本轮文档差集审查及剩余完整回归/总对账的安排；不扩建平台、不重复已充分通过的HTTP、不直接封板。
