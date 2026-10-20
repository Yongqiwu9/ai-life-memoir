# Part 9.6-C2 — 专项 HTTP/ASGI＋PostgreSQL 16.15 验证合同 V1.0

- 日期：2026-10-17。
- Status：VALIDATION CONTRACT FROZEN；执行状态：NOT RUN。
- 基线：master @ `c8824b3c2c1d7c9ae6d633461787431166cd7a07`，加当前已批准的 36 路径 C2 实施工作区。
- 实施合同：[Session Text Integration V0.4](../04_AI设计/Part9.6-C2_Session-Text-Integration_Implementation-Contract_Draft_V0.4.md)，SHA-256：`6589c552f896e40f47a789a7fdae63f2bc91ef18485ae04e75c6aa462918a68c`。
- 本轮授权：合同文档归档与静态核对；不执行测试、HTTP、数据库连接、Docker、迁移或 Git 写操作。
- 冻结的是验收范围、隔离规则、停止和清理要求。执行入口、补验源码及实际资源分配仍须专项审查与批准；本合同不自动授予执行权限。

## 1. 目标与证据边界

补齐当前 C2 的专项接口、真实 PostgreSQL 迁移/约束/竞争证据；不重复以全量回归代替差集验证。

已有结果仅作历史输入：Backend 定向离线 152 PASS（86＋22＋44），不是完整 Fast；旧列数断言已修正且定向只读复审通过。此前 AI Service 纯合成 360 PASS 的执行时点独立保留，不解释为本次 HTTP 通过。

本合同执行前所有 HTTP、PostgreSQL、清理结果均为 NOT RUN。17／13 是源码 manifest 数量，不是执行结果。D01–D73 的完整封板对账另行完成，本专项通过也不能自动宣布全部合同验收通过。

继续排除真实个人资料、真实语音、真实 Provider、真实 Consent 流程、C3 激活、C4/C6、生产、历史 UNKNOWN 资源及通用 BM-01 provisioning。不得关闭这些限制。

## 2. 精确资源与文件边界

### 2.1 本轮唯一新增项目文件

本合同自身。README、路线图、日志、运行代码、测试、workflow、迁移源码、配置及 Git 暂存区均不修改。

### 2.2 后续批准执行时的只读输入

| 输入 | 用途 |
| --- | --- |
| `apps/backend/tests/test_dialogue_api.py` | Backend 专项 ASGI |
| `services/ai-service/tests/test_dialogue_http.py` | AI Service 独立 ASGI |
| `apps/backend/tests/test_dialogue.py`、`services/ai-service/tests/test_dialogue_wire.py` | 既有合成 fixture 与 DTO helper |
| `apps/backend/tests/integration/test_dialogue.py` | 固定 17 项运行用例 |
| `apps/backend/tests/integration/test_dialogue_migration.py` | 固定 4 项 Manager 迁移用例 |
| `scripts/ci/run_dialogue_postgres.py` | 17／13／4 manifest、CI 管理生命周期静态参考 |
| C2 的 Model、Schema、CRUD、Service、Router、迁移及其历史迁移链 | 被验证实现，只读使用 |
| 根/Backend AGENTS、相关 pyproject、Alembic 配置和既有隔离合同 | 规则和配置结构；不得加载真实环境文件 |

启动器放在本次新建的项目外受保护证据目录，仅完成该次固定执行；不扩建通用平台，不修改既有启动器，不伪造 GitHub 环境绕过 CI 门禁。外部启动器源码和哈希必须先审查，再批准运行。

现有用例不足时，补验设计只允许提出对上述两个 HTTP 测试文件或 PG 专项测试文件的精确增补；须另获源码修改批准并复审。合同归档本身不授权修改这些文件，也不允许静默减少验收。

### 2.3 保护对象

保持现有 C3/BM-01、AGENTS 修改、其他未提交文件、16 个历史模板删除、untracked `ad`、ignored `.env.test`。不读取 `ad`、`.env`、`.env.test`、真实密钥或个人正文。不暂存、提交、推送、恢复、重置、清理项目文件。

## 3. 执行前置门禁

1. 记录实际 HEAD、工作区/暂存区状态、合同、36 路径实现、测试和启动器 SHA-256；保留原保护文件快照。若与审查快照不同，解释差异并重新审查受影响范围。
2. 同一执行身份创建唯一证据目录，核验绝对路径、非链接、可写、访问权限及写入/读回；目录失败时不启动测试。不改变工作区或系统临时目录的全局权限。
3. Python 使用已核验的绝对路径及版本；禁用字节码、pytest 缓存、第三方插件自动加载；只加载必要测试 fixture，不载入全局 conftest 的真实数据库配置。
4. 白名单环境仅含运行必要系统变量、一次性合成 JWT/完整性密钥、精确分配信息。禁用 dotenv、默认凭据搜索和真实 Provider。不得打印带密码 URL、完整环境或原始敏感异常。
5. Manager 和 Runner 的计划命令、执行身份、工作目录、环境字段（不含密钥值）、证据路径及超时预算必须在启动前写入非敏感 manifest。创建进程后、任何通信或等待前，立即保存原始进程对象/原生句柄，并补记实际 PID、创建时间与登记结果；句柄不序列化进公开 manifest。登记失败按 UNKNOWN 保留，不继续调度或自动清理。测试发现/收集也属于未来执行授权，不在本轮运行。
6. 不适配门禁时 STOP；不得修改业务隔离、扩大管理员权限、设置伪造 CI 标志或跳过用例取得绿色结果。

## 4. HTTP/ASGI 验收合同

### 4.1 隔离与入口

- Backend 每个参数化实例创建独立内存 SQLite：`sqlite://`、`StaticPool`、`check_same_thread=False`、FK ON；每例新 Engine/Session/合成用户图，结束 rollback/close/dispose，无跨例可变数据。
- 使用既有 `graph` fixture，但从新授权的 HTTP 启动入口加载；不能直接使用禁止所有 socket 的离线入口并暗中放开限制。
- TestClient 在进程内驱动 ASGI；允许事件循环所必需的内部 socketpair。不得创建对外监听，不使用 HTTP 访问真实服务、真实数据库或 AI Provider；任何外连尝试均失败。
- Backend 与 AI Service 分开进程、各自应用命名空间。AI Service 使用独立合成 credential 和确定性 Provider，不跨应用 import 运行时代码。
- 允许替换认证依赖建立合成 actor，以验证服务 owner scope；未认证分支保留 401 检查。这不构成完整 JWT 登录链或部署应用全部 middleware 已通过的证据。
- Backend 的纯 C1 JSON 子进程仍禁止联网；20 秒通信限额与 UNKNOWN 保留规则不变。

### 4.2 当前测试与覆盖差集

静态展开：Backend 现有 14 项参数化实例，AI Service 现有 6 项，执行前须以实际精确节点集合对账，不能只核对数量。

| 编号 | 必须覆盖 | 现有来源／需要补齐的证据 |
| --- | --- | --- |
| H01 | DEBUG true/false：start 202→apply 201→state；换 actor 404 | 现有 Backend create/start/apply 测试 |
| H02 | 禁止内部 callback、布尔 version、额外正文等非法输入；422 不回显 | 现有 invalid requests，两模式 |
| H03 | dependency/endpoint/response serialization 异常固定 500/code；不含正文、SQL、token、traceback | 现有三边界×两模式 |
| H04 | 缺认证 401、坏 JSON/UUID 422，错误不回显 | 现有 malformed 测试，两模式 |
| H05 | 内部 credential 缺失/错误 401、合法 200 且 input_digest 绑定 | 现有 AI Service 3 项 |
| H06 | 默认关闭 503、超限 413、非法结构 422、正文不泄露 | 现有 AI Service 3 项 |
| H07 | 全部七个路由：state、commands create/read/apply、messages、delivery start/complete | 现有源码未形成完整接口链；需专项合成 HTTP 场景补验 |
| H08 | text 保存→queued command→apply；同 key 重放不多写；payload 冲突拒绝；对账只读 | 同上；以响应与数据库副作用/调用次数共同断言 |
| H09 | 主动 request_response→可信合成 dispatch→delivery start/complete；准确区分 ready/started/completed | dispatch 仅在可信测试驱动中执行，不增加公开 callback；经七个真实路由序列化 |
| H10 | pause→暂停中保存文字→resume 显式同步→end；结束后新文字拒绝、迟到输出不恢复 | 使用真实 API，版本从实际响应读取，不伪造 C1 checkpoint |
| H11 | 消息、命令 ID、apply、delivery 的跨 actor/跨 Session 拒绝，来源失效与过期 delivery token 拒绝 | 现有 state-only owner 测试不足；不得据此宣称全路由隔离通过 |

H07–H11 固定为执行前补验差集，不预报通过数量。补验场景/节点须先归档精确清单、只读审查与实施批准；不扩大为新功能、真实业务资料或全应用端到端部署验证。新增合成断言不允许改变产品行为。

### 4.3 HTTP 成功条件

精确节点均执行，0 failed/error/skipped/xfail，H01–H11 有代码与执行证据对应；全流程断言至少包含响应状态/字段、原文/assistant 写入数、Turn/State 版本与 fence、Client 调用次数、终态和错误无敏感标记。不得用“请求未抛异常”替代断言。

## 5. PostgreSQL 16.15 资源与身份合同

### 5.1 基础设施复用

优先只读核验既有容器 `ai-memoir-c3-pg16`、`127.0.0.1:55432`。它们仅是候选，不是当前已核验事实或操作授权。必须核验容器完整 ID、image ID、端口映射、集群 system_identifier、实际 `SELECT version()` 与 `server_version_num=160015`。版本不符立即 STOP，不运行验收。

不创建新容器、不启停/重启容器、不操作卷、历史角色/密码/数据库 ACL/模板；历史库 `ai_life_memoir_c3_test` 绝非测试目标。既有 CI Manager 明确只支持 GitHub hosted Linux 独占服务，并拒绝本地 55432；不得直接在本地使用 `--ci-manager` 或削弱其 context_gate。

### 5.2 每次分配清单

每次获准真实执行使用新 UUID v4（重跑须新分配，不自动重跑）。沿用当前 fixture 的精确身份格式，名字中的 `ci` 不意味着本地可以伪造 CI：

- 数据库：`ai_memoir_dialogue_ci_test_<uuidhex>`；TEMPLATE template0。
- 专用 owner：`d_ci_owner_<uuidhex>`。
- 受限 Runner：`d_ci_runner_<uuidhex>`。
- 分配变量：`DIALOGUE_ALLOCATION_RUN_ID`、`DIALOGUE_ALLOCATED_DATABASE`、`DIALOGUE_RUNNER_ROLE`、`TEST_DATABASE_URL`；逐项与 manifest、实际 current_database/current_user/owner OID 核验。
- 记录集群、数据库/角色 OID、数据库 marker、创建时间、运行 UUID、所有权及分配前不存在证据。不记录密码。
- CREATE DATABASE 非事务 DDL；冲突、创建结果未知或 OID 未可靠记录时不自动认领/重试/删除。

### 5.3 Manager 与 Runner

可信 Manager 的管理连接只用于该次分配、权限检查与精确清理；能力与任务权限分开。已有管理身份必须现场核验，不把管理凭据交给 Runner。持有本次管理 advisory lock；不宣称能防御其他超级用户并发操作。

迁移子进程使用新 owner 的仅本次库连接；owner 无 SUPERUSER/CREATEDB/CREATEROLE/BYPASSRLS/REPLICATION，不拥有其他资源。仅迁移时临时 LOGIN；迁移完成撤销 LOGIN/密码并核验无 owner 会话。Manager 后检需 owner 连接时按同样规则单独短时启用，绝不交给 Runner。

Runner 为独立随机一次性凭据 LOGIN，无超级用户、角色成员关系、CREATEDB、CREATEROLE、BYPASSRLS、REPLICATION、数据库/schema/表所有权、DDL、TRUNCATE 或清理能力。仅获新库 CONNECT、必要 schema USAGE、测试表 DML 与必要序列权限；新库撤销 PUBLIC CONNECT/TEMP/CREATE 和 public schema CREATE。

Runner 不能调用迁移、Docker、管理入口或读取 Manager 凭据；用例只操作本例 UUID 合成图，竞争线程各自独立连接并真实提交。默认 `expire_on_commit=True`。固定可信测试源码不等于抵御恶意 Python 的 OS 沙箱，报告不得夸大。

### 5.4 历史库连接隔离与当前适配阻塞

历史库可能通过 PUBLIC CONNECT 授权。仅撤销新 Runner 的显式 ACL 不能阻止连接。不得修改历史库 ACL 来让测试通过。

候选本地方案：经另行明确批准后，只增加匹配本次 Runner 的精确 HBA 规则，允许实际核验客户端地址访问本次库（SCRAM），其他数据库/连接方式拒绝；原规则逐字保留，核验语法与优先级后 reload，不重启。执行结束移除精确本次规则并核验恢复。不得继承旧 B 任务的 HBA 授权。

必须记录两类证据：SQL 角色权限检查，以及实际连接本次库成功、历史库/postgres/template1 拒绝；拒绝探针不得读取正文。

**已确认执行阻塞**：现有 `test_runner_is_restricted` 对 postgres/template1 断言 `has_database_privilege(...,'CONNECT') is False`。HBA 拒绝不改变该 SQL ACL 结果；历史 PUBLIC CONNECT 存在时，本地方案不能原样满足此测试。不得谎报 HBA 等价于 SQL ACL 撤销、跳过测试或修改历史 ACL。

真实执行前须审查并批准最小适配：保留无管理员/DDL权限断言，精确区分“ACL 拒绝”与“本次 HBA 有效连接拒绝”的隔离证据，同时保持 CI 独占集群原有更严格 ACL 验证。只读分析不能自行修改现有用例；适配仍计入原 17 节点中的同一节点，不额外计为竞争。无法完成适配或连接隔离核验则本地 PG BLOCKED。

## 6. PostgreSQL 固定验收清单

### 6.1 Manager 迁移专项（独立 4 项，不计入 17／13）

在唯一新库 fresh upgrade 到精确 `c296a4e8d102`，先核验父链 `b196f0d47a21`、单一 heads/current/check；随后按固定顺序运行：

1. `test_legacy_upgrade`：合成 v1/v2 State/Turn/Message 原字段和值不变；新增字段保持 NULL，不补认授权。
2. `test_marker_downgrade_refusal`：实际有效 v3 marker 阻止回退且 schema/head 保留；表/字段防护中被父约束涵盖分支以静态约束证明说明，不制造孤儿。
3. `test_legacy_downgrade_reupgrade`：无 C2 数据时回退父版本、旧 10/29 列及旧约束恢复，再升级；不宣称此测试已穷尽所有含数据回退情形。
4. `test_schema_matches_metadata`：真实 Alembic check。

各例只使用自身合成数据，迁移例之间确认清理和恢复精确 head；失败/退出不确定不得继续后续迁移或 Runner。migration fixture 的 finally 不替代 Manager 对退出与最终 schema 的核验。

**VC-01 执行控制澄清：** 当前迁移 fixture 的 `finally` 无条件执行 upgrade，部分测试本体的 `finally` 也执行删除/提交；PG fixture 将线程 UNKNOWN 转为 pytest 失败，但批量入口仍可能继续下一例。这些入口尚不满足本合同，不能仅依赖外部 Manager 在子进程退出后检查，或仅增加 `-x` 后宣布已解决。

未来须单独批准并复审最小测试适配，明确覆盖 `tests/integration/test_dialogue_migration.py` 的 fixture/测试本体清理、`tests/integration/test_dialogue.py` 的 UNKNOWN 传播，以及项目外专项入口的逐例调度；不涉及业务代码或通用平台。普通失败和 UNKNOWN 必须分别记录：当前例失败即不启动下一例；检测到进程/线程/事务/DDL 结果 UNKNOWN 时，必须先形成 Manager 可识别的 RETAINED 状态，再阻断 fixture/测试本体后续自动 schema 恢复、数据删除、提交及其他 SQL。无法可靠报告时同样按 UNKNOWN 保留。

只有当前例执行者与事务结局均确认后，才能进入确定性普通 teardown；Manager 再核验退出、最终 schema 和资源身份，决定后检及精确清理。原先无条件 `finally` 写入必须完成适配并定向复审；未完成前真实 PG 执行保持 BLOCKED。本轮只澄清合同，不修改上述源码或启动入口。

### 6.2 Runner 专项 17 项

以下节点均位于 `apps/backend/tests/integration/test_dialogue.py`，是精确名称集合；竞争列为“是”的 13 项必须实际执行且通过，不能靠 collection、顺序模拟或 skip 替代。

| # | 节点 | 竞争 |
| --- | --- | --- |
| 1 | `test_runtime_column_constraints` | 否 |
| 2 | `test_runner_is_restricted` | 否 |
| 3 | `test_parent_lock_sequence` | 是 |
| 4 | `test_parallel_same_key` | 是 |
| 5 | `test_normal_cas_race` | 是 |
| 6 | `test_stop_publish_race` | 是 |
| 7 | `test_typing_delivery_race` | 是 |
| 8 | `test_claim_crash_once` | 否 |
| 9 | `test_delivery_unknown_readback` | 否 |
| 10 | `test_source_publish_race` | 是 |
| 11 | `test_parent_child_preparing` | 是 |
| 12 | `test_old_generation_after_stop_cannot_poison_new[ready]` | 是 |
| 13 | `test_old_generation_after_stop_cannot_poison_new[timeout]` | 是 |
| 14 | `test_unknown_first_cannot_be_cleared_by_other_connection` | 是 |
| 15 | `test_callback_publication_vs_delivery` | 是 |
| 16 | `test_pause_rpc_vs_later_safety_control[typing_started]` | 是 |
| 17 | `test_pause_rpc_vs_later_safety_control[record_only]` | 是 |

第 15 项验证 ready 发布与 delivery 并发后不会留下永久 busy；16/17 验证 pending pause 不被后续安全控制吞掉。重复 pause 作废未发布 resume（C2-IR-T03）已有合成离线回归证据；本次不将其声称为新增 PG 节点，若审查要求 PG 补例，须显式修订 manifest 和合同再批准。

第 1 项须核验实际 CHECK/FK/unique SQLSTATE `23514/23503/23505`、rollback 后原值/数量，以及本次两个 CHECK 的 NULL 负例确实由正确约束拒绝。不能使用 Python DTO 拒绝替代数据库约束结果。

竞争证据记录节点、独立连接/必要 backend PID、barrier/锁等待或明确交错窗口、最终事务结果与业务不变量；保留真实 PostgreSQL 父行锁等待证据。两项 claim/readback 顺序测试仍必须通过，但不计为竞争。

Runner 前后 Manager 核验 current/check；全过程精确 revision，不以未来可能改变的泛化 head 代替目标。用例 manifest 缺失、多余、重复、skip、xfail、失败或数量不符均不能 PASS。

## 7. 超时、停止与 UNKNOWN

| 项目 | 上限与行为 |
| --- | --- |
| PG connect | 5 秒；失败停止该步骤，不自动重试分配 |
| Runner SQL | statement_timeout 8000ms、lock_timeout 4000ms，遵循既有 fixture |
| Manager 单 SQL | statement_timeout 最多 15000ms，不能超过本次剩余预算 |
| 固定单步 SQL/权限只读检查 | 15 秒；返回不确定立即停止 |
| 竞争同步 | 沿用既有节点的 3/5/8/10/15/20 秒有限等待；不能临时拉长使失败消失 |
| 纯 JSON C1 子进程 | 20 秒，保留原退出不确定处理 |
| HTTP 单个测试子进程 | 180 秒；Backend/AI Service 分开计时 |
| Manager migration 用例阶段／Runner 17 项阶段 | 各 180 秒，子进程另保存 receipt |
| HTTP＋PG 整次执行 | 900 秒总预算，以 monotonic 记录；清理另留最多 120 秒核验预算 |

超时不等于已退出，也不证明回滚。停止发起后续测试/SQL，使用保存的原生句柄、创建时间和原有进程对象核验退出/EOF、线程及子进程归零、receipt 与退出码一致。不得仅凭 PID 不存在或主进程退出判断全部结束。

进程/子进程/连接/事务/分配身份/证据完整性任一未知即 UNKNOWN→RETAINED/BLOCKED；不自动重复请求、重新分配、恢复业务或清理其资源。禁止任意 kill、DROP DATABASE FORCE、pg_terminate_backend、前缀清理。需要终止或恢复时另行定向授权。

已确认普通测试失败且所有执行者/事务均有确定结局，可由 Manager 正常清理，再报告 TEST FAILED / CLEANUP CONFIRMED；不得因为用例失败就无条件保留，也不得在 UNKNOWN 时为满足清理指标强删。

## 8. 精确清理合同

1. 停止提交新工作，确认 Runner/迁移/HTTP/C1 所有相关进程、线程、子进程退出，输出及 receipt 完整；Manager 只保留用于核验和清理的管理连接。
2. 复核容器/集群身份、库名/OID/owner OID/marker 与本次 manifest；变化、同名替换或意外依赖时 STOP。
3. Manager 先核验本次库身份和全部身份的既有会话，关闭本次库新连接，再次核验目标数据库全部身份的会话均为零，包括 owner、Runner、Manager 后检及任何意外连接；有残留或结果未知即停止保留，不终止会话。确认归零后普通精确 DROP DATABASE，不 FORCE、不自动重试不确定 DROP。
4. 从同一集群目录核验该库名字与 OID 均不存在；再精确清理本次 owner/Runner，确认名称与 OID 不存在且未留下额外依赖。不执行 DROP OWNED 波及其他库。
5. 如专项批准过 HBA 规则，核验原始哈希及并发变化，仅移除本次精确段、reload、核验规则移除及其余原文保留。不能覆盖他人的更新。配置恢复失败整体 cleanup 不能 PASS。
6. 临时凭据在所有持有者确认退出后移除；只清理本次 manifest 中已核验归属的文件，不递归扫描临时目录。保留脱敏 manifest/JUnit/退出/清理证据；不保留 API key、密码、原始正文或带凭据 URL。
7. 核对历史资源元数据、项目文件哈希、Git 状态：除另行批准的补验源码/合同文件外无变动；旧 UNKNOWN 不触碰。暂存区和历史排除项保持原样。

## 9. 证据包与报告合同

证据目录由未来执行时新分配，不复用旧探针。至少保存：

- 合同/实施/启动器/固定测试 manifest 与哈希、实际解释器版本、执行身份及 UTC 时间。
- 非敏感 allocation manifest：run UUID、容器/image/集群标识、endpoint、库/角色/OID、marker、权限证据、状态变更。
- HTTP Backend 与 AI Service 分开的精确 collection、JUnit、退出与清理；H01–H11 对应表及所有未覆盖项。
- PG migration 4 项与 Runner 17 项独立 JUnit，竞争 13 项逐节点实际执行证据，实际版本与 SQLSTATE、迁移前后 current/check。
- 每个进程的身份/父子关系/退出码/EOF/receipt；未知项不得抹除。JUnit 公共版本移除原始异常正文，受保护原始诊断仅限必要合成数据，不记录凭据。
- 库/角色不存在、HBA 恢复（若获批）、临时密钥移除、历史资源与工作区保持证据。

最终分别给出 HTTP、AI Service ASGI、Manager Migration、PG Runtime 17、PG Competition 13、Cleanup、保护范围和静态审查结果。字段至少含 collected/passed/failed/errors/skipped/xfail、actual version、NOT RUN/BLOCKED/RETAINED。

只有全部必需节点与覆盖项通过且资源精确清理核验通过，才写 SPECIALIST VALIDATION PASS。运行通过但清理不确定写 VALIDATION PASSED / CLEANUP UNKNOWN — OVERALL BLOCKED；任一阶段未运行不得宣称专项完整通过。

## 10. 审查与执行顺序

1. 本合同冻结并归档；本轮静态自查，不冒称独立审查。
2. 独立审查合同、HTTP H07–H11 差集和本地 PG 权限断言适配方案；先批准必要最小测试/外部启动入口增补，完成后定向复审。
3. 用户批准精确执行资源/入口/超时/清理及必要 HBA 专项范围后，先 HTTP/ASGI；失败则停止后续 PG，报告根因。
4. HTTP 满足合同后执行真实隔离 PG 16.15：Manager 分配/迁移 4 项→受限 Runner 17／13→Manager 后检/清理。
5. 独立复核执行与清理证据，再同步文档；不自动进入暂存、封板、commit/push 或下一阶段。

### 本轮状态

**VALIDATION CONTRACT FROZEN — NOT EXECUTED**。

执行前仍需关闭的真实缺口：H07–H11 的完整 HTTP 场景与精确节点清单、本地 ACL/HBA 断言兼容方案、专项外部入口审查及资源/HBA 实际授权。其余现场版本/身份/权限检查为必须执行的门禁，不应预先当作通过。
