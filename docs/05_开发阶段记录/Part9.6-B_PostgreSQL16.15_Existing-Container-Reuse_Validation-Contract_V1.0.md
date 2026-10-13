# Part 9.6-B — PostgreSQL 16.15 现有容器专项复用验证合同 V1.0

> 2026-10-14 补充：用户已另行授权合成Legacy升级/downgrade专项，并执行18个固定脚本场景通过（非18个pytest用例）；最终current/check通过，精确资源清理核验通过。run UUID：32c3f830-df9a-4686-a6c5-31ebda71f986。证据目录：C:/Users/Administrator/AppData/Local/Temp/memoir-pg-legacy-892f1daa80584aa4a0d63784204f6548。独立实现复核PASS WITH FINDINGS；B32/B33/B52并发及未单独覆盖的回退分支保持验证缺口。此补充不改通用BM-01门禁，不宣称全57项完成。

## 1. 状态与授权

- Status: CONTRACT REVIEWED / SCOPED POSTGRESQL VALIDATION PASSED
- PostgreSQL acceptance: 本合同第 6 节的专项范围通过；不代表完整 9.6-B 封板或生产就绪。
- Baseline: master @ 6c12e96e4f83ada7cb7c7dd60fec4283269f8700，加当前未经提交的 9.6-B 实施。
- 本合同仅约束一次 9.6-B 专项验证，不修改通用隔离平台，不关闭 BM-01，不宣称其真实 provisioning 已通过。
- 用户已授权制定现有容器专项复用合同，并在审查通过后执行验证。
- 用户已明确批准仅本次新 Runner 的认证规则变更、reload、结束后移除及核验恢复。实际核验失败仍须 STOP。
- 当前仅新增本合同文档；禁止暂存、提交、推送及修改其他项目文件。

## 2. 已核验事实

2026-10-13，只读 Docker 与系统目录检查：

| 项目 | 实际结果 |
| --- | --- |
| Docker context | desktop-linux |
| Container ID | 1e4f6a0a344c9eee9de80847b66e096fc5bfa76a2854faa485b7bb81ce80db73 |
| Container name | ai-memoir-c3-pg16 |
| Image | postgres:16.15 |
| Endpoint | 127.0.0.1:55432 -> 5432/tcp |
| SQL server_version_num | 160015 |
| 已有管理身份 | c3_test_user，SUPERUSER / CREATEDB / CREATEROLE / BYPASSRLS |
| 历史数据库 | ai_life_memoir_c3_test |
| 历史数据库 ACL | DEFAULT；不能证明新 Runner 无 CONNECT 权限 |
| postgres 角色 | 不存在；不得据此创建或修复历史角色 |

镜像标签不能代替 SQL 版本验证。system_identifier、容器镜像 ID、实际 HBA 规则、数据库 OID 等仍须执行前核验；不得凭本表虚构证据。

通用 PostgreSQL adapter / registry 当前拒绝 55432；bootstrap.sql 要求新空集群并修改模板/全局 ACL，因此不适用于本合同。禁止调用或修改这些入口来规避门禁。

本合同限定人工可信 Manager 的一次性资源分配、原生进程验证与清理，不复用未经真实验证的通用平台执行结论。

## 3. 保护范围

不得修改、迁移、读取业务正文或删除历史数据库；不得改变历史角色权限、密码、历史库 ACL、template0/template1、容器生命周期、镜像、卷、网络或端口。

仅允许：
1. 审查通过且连接隔离专项批准后，创建一个 UUID v4 命名的全新临时数据库和两名全新角色。
2. 在该数据库内执行已有 Alembic 源码及合成数据用例。
3. Manager 清除本次可核验分配资源。

禁止使用历史 .env / .env.test、生产密钥、真实个人数据、真实 Provider、外网和其他测试运行资源。

未知旧探针继续 UNKNOWN/保留，不作为本次资源，不做推断清理。

## 4. Manager / Runner / 所有权

### 4.1 可信 Manager

- 已有 c3_test_user 仅作为可信管理入口，通过精确 container ID 的本地 psql，且仅操作本次白名单资源。
- 不把该角色凭据、超级用户连接或 Docker 操作能力交给 Runner。
- Manager 先记录集群 system_identifier、版本、容器 ID、运行 UUID、数据库名及分配前不存在证据。
- 新建专用 NOLOGIN owner 角色，名称 `b_owner_<uuidhex>`；不赋予 SUPERUSER、CREATEDB、CREATEROLE、REPLICATION、BYPASSRLS。
- 在线 Alembic 需要独立管理连接：只在 Manager 迁移期间，为本次新 owner 临时设置随机密码并启用 LOGIN；URL 仅指向本次库。测试启动前撤销 LOGIN 并清空密码，核验无 owner 会话。此凭据不得交给 Runner；不用历史凭据，也不新增第三个角色。
- 临时库名 `ai_memoir_b_test_<uuidhex>`，TEMPLATE template0，owner 为上述 NOLOGIN 角色。
- Manager 使用受控管理连接在这个库执行迁移，SET ROLE 为新 owner；每一步确认 current_database / current_user / session_user。
- 可信 Manager 持有覆盖分配到清理的 session advisory lock，并记录锁键；该锁仅协调遵守合同的管理者，不防御其他超级用户。
- Manager 有能力创建/清理，任务权限仅限精确分配资源；不得按名称前缀扫描清理。
- 已有历史角色权限不变。

### 4.2 受限 Runner

- 新建 `b_runner_<uuidhex>` LOGIN，随机一次性密码；无管理员权限，不加入任何角色，不拥有数据库/Schema/表。
- 只获临时库 CONNECT、run_data/public 实际迁移 Schema 的 USAGE，以及用例所需表 SELECT/INSERT/UPDATE/DELETE、序列 USAGE。
- 无数据库 CREATE、Schema CREATE、表 DDL、TRUNCATE、角色管理或清理权限。
- 新建库撤销 PUBLIC 的 CONNECT/TEMP/CREATE，并撤销该库 public Schema 的 PUBLIC CREATE；仅改变新库。
- Runner 不运行 Alembic；测试不执行 provisioning。
- 连接配置仅交给固定测试进程，凭据不写命令行、日志、Git、报告或项目文件。
- 临时凭据载体由同一执行身份创建，访问 ACL 最小化；确认子进程退出后清除，失败则保留受保护证据。
- Runner 不读取管理凭据；不运行 Docker、psql 管理命令或外网请求。
- 本次固定合成测试源码不视为恶意 Python；环境变量过滤不宣称是 OS 安全隔离。

### 4.3 跨数据库连接门禁：实施阻塞

PostgreSQL 无“对单一角色拒绝 PUBLIC 已授予 CONNECT”的数据库 ACL。不得仅 REVOKE Runner 的显式权限后声称历史库已隔离。

已批准最小方案，仅用于本次新 Runner：
- 在实际认证配置规则之前添加仅匹配本次新 Runner 的规则：
  - 允许其从实际核验的本次客户端地址连接精确临时库，使用 SCRAM；
  - 对该 Runner 的其余 TCP/本地数据库连接一律 reject。
- 必须核验 Docker 端口转发后服务端实际客户端地址，不能猜为 127.0.0.1。
- 仅增加新 Runner 的规则，原规则逐字保留；禁止改变历史用户的匹配结果或全局 trust。
- 修改前保存原配置哈希与受保护备份，规则语法检查成功后 reload；不能重启容器。
- 验证新 Runner 可连接临时库，不能连接历史库、postgres/template1 或其他数据库。
- 无有效变更权限、无法唯一定位认证配置、无法确认规则优先级、并发配置变更或连接拒绝验证失败：STOP，不运行业务验收。
- 配置恢复属于独立核验的精确本次规则清理，不能覆盖其他人的变更。

替代方案须证明同等 SQL 隔离能力，并经合同审查；不得通过修改历史库 ACL 或交给 Runner 超级用户实现。

## 5. 分配与证据

每次真正获准执行生成一个新的 UUID，不复用历史库或其他运行 UUID。本次只有一个临时库；多连接测试使用其独立已提交合成图，各例不得复用可变数据。

持久化非敏感 manifest：
- UUID、容器 ID、镜像 ID、system_identifier、版本、endpoint；
- 临时数据库名/OID、owner/Runner 名及 OID；
- owner marker、创建时间、状态；
- 执行前合同、迁移、测试、运行时代码哈希；
- 各进程 PID、原生创建时间、句柄退出结果；
- 每步骤结果、权限核验、配置变更哈希（如批准）、清理证据。

状态：PLANNED -> ALLOCATED -> MIGRATED -> RUNNING -> CLOSING -> CLEANED；任意不确定转 RETAINED/BLOCKED，不自动重试创建/删除。

CREATE DATABASE 是 autocommit DDL，不能声称可由事务回滚。名称不存在检查后发生冲突、创建结果不确定或创建到 OID 记录之间故障，立即停止；不自动认领同名资源。

## 6. 验证顺序与范围

1. 只读核验容器、真实 SQL version() / server_version_num=160015、集群身份、Manager 能力、历史资源元数据。
2. 核验批准后的连接隔离方案；分配精确新角色与新库，核验所有权/权限与 marker。
3. Manager 在临时库执行 `alembic upgrade b196f0d47a21`，再 current/check；不使用可能引入范围外分支的泛化 head。
4. Runner 验证数据库名、角色、实际版本、权限、head，任何不符立即 STOP。
5. 仅执行现有 `apps/backend/tests/integration/test_memory_workflow.py`：
   - 源码展开预计 28 个参数化实例（以实际只读 collection 为最终核对，差异先解释）；
   - 包含双连接 Candidate 审批，以及 Memoir 与 proof/body 清除的两种提交顺序；
   - 开启精确 MEMORY_B_MULTI_CONNECTION_RUN_ID，不能跳过并发用例后宣称通过；
   - 使用既有每例回滚 fixture；多连接用例的已提交图必须使用全新 UUID，后续例不复用。
6. Manager 再执行 Alembic current/check。
   这两个只读检查由 Manager 启动独立进程，使用本次受限 Runner 的目录读取权限；测试进程不调用 Alembic，也不获得 owner 凭据或 DDL 权限。
7. 原生确认所有相关进程退出、测试线程结束、Runner 数据库会话归零，随后清理。
8. 只读核对项目/Git 状态和保护文件哈希，确认仅合同文档变化。

传入的 allocation metadata：
`MEMORY_B_ALLOCATION_RUN_ID`、`MEMORY_B_ALLOCATED_DATABASE`、`MEMORY_B_RUNNER_ROLE`、`MEMORY_B_MULTI_CONNECTION_RUN_ID` 与 TEST_DATABASE_URL 必须逐字段与 manifest 一致。

配置来源必须阻断项目 dotenv 与真实密钥读取；日志脱敏。固定用例不等于授权执行整个 integration suite。

## 7. 迁移证据边界

本次验收 fresh upgrade/current/check + 现有 PostgreSQL 用例。历史 fixture 升级、downgrade 拒绝及纯 Legacy downgrade 属于单独验收，当前不得标为通过；不得读取真实历史库来制作 fixture。

若需要该补充验收，应使用合成 Legacy 数据与单独范围确认。本合同不自动扩大为全项目迁移覆盖。

## 8. 退出、失败与清理

- 进程使用保存的原生句柄及精确身份，输出 drain、退出码、EOF 与证据写入均须核验。
- 步骤设有限超时；超时不是退出证据。退出不确定保留数据库/角色/证据，不进行强制清理。
- 禁止任意 PID kill、DROP DATABASE FORCE、终止其他数据库会话或前缀清理。
- 可确认测试失败且所有执行者已退出时，仍由 Manager 按精确身份清理；测试失败不必留下可确定的临时资源。
- 清理前再次核验 system_identifier、数据库名/OID、owner OID、marker 与 manifest；任一变化 STOP。
- 禁止新连接后，再核验该库无会话，普通 DROP DATABASE 精确临时库；不自动反复 DROP。
- 数据库不存在核验成功后，清理仅本次新角色；角色存在额外依赖、OID 变化或 DROP 结果不确定时保留并报告。
- 如批准新增 HBA 规则，在 Runner 退出且角色清理后移除精确规则，保持其余内容；并核验 reload 与最终配置。
- 若 HBA 清理失败，不能报告整体 cleanup PASS。
- 普通测试、迁移、权限核验通过且全部分配资源清理核验成功，才可报告 PostgreSQL 专项 PASS。

## 9. 合同静态审查

本会话静态自审，非独立第三方审查：

| 核查项 | 结论 |
| --- | --- |
| 现有版本与基础设施 | 已只读核验；执行前需再核验身份 |
| 历史库、角色、模板保护 | 明确 |
| Manager/Runner 分离 | 已定义；尚未分配实测 |
| PUBLIC CONNECT 的绕过风险 | 已识别；连接隔离方案尚待批准 |
| 迁移、测试范围 | 精确限制为 B revision 与单一测试文件 |
| 并发与每例隔离 | 依照现有源码；须实际运行证明 |
| 清理权限与不确定退出 | 明确；尚未实测 |
| 通用 BM-01 门禁 | 保持；本合同不激活/改写通用平台 |

Verdict: 静态合同自审 PASS，专项认证配置变更已获用户明确批准；不代表运行验证通过。
凭据、集群标识、配置位置等执行前技术核验失败均必须 STOP，不允许实现者代作肯定判断。

## 10. 最终报告要求

报告分别列出：
- 合同审查结果、真实 PG 版本、精确库/角色（不含密钥）；
- Fresh migration/current/check；
- 用例 collected/passed/failed/skipped，真实双连接锁等待证据；
- 每步骤进程退出核验；
- 数据库不存在、角色清理、配置恢复；
- 历史资源及项目/Git 保持情况；
- 不含本次范围的 Legacy/downgrade、HTTP、真实 Provider 与生产边界。

未执行则写 NOT RUN；资源未清理则写 RETAINED，不以 SQLite 或静态审查替代 PostgreSQL 证据。

## 11. 实际执行结果 — 2026-10-13

- 最终运行 UUID：d67e00b5-9d8f-406e-a2a1-26fd3f98d2bb。
- 实际 SQL 版本：PostgreSQL 16.15 / 160015。
- 本次库：ai_memoir_b_test_d67e00b59d8f406ea2a126fd3f98d2bb；已核验不存在。
- Fresh upgrade 到 b196f0d47a21：PASS。
- 测试前 current/check：PASS；测试后 current/check：PASS。
- 现有专项用例：28 passed in 2.68s；无跳过；包含真实双连接审批与 Memoir proof/body 清除的两种提交顺序。
- Runner 对历史库、postgres、template1 的连接均被实际 HBA 拒绝。
- 测试进程 exit=0、无残留测试线程；Manager 锁进程 exit=0。
- 两名本次角色已核验不存在；原 HBA 字节恢复并 reload，清理 PASS。
- 319 个既有非敏感受保护文件哈希未变化；HEAD 不变，暂存区为空，16 个历史删除、ad 和 ignored .env.test 保持原状态。
- 准备阶段曾因临时脚本 CIDR/标记核验错误停止；只读确认身份和退出后，已精确清理该次资源。
- 首次用例执行 2 passed / 26 failed，原因是临时入口漏加载已有 models_import；其资源已清理。只补齐临时入口初始化后，全新隔离运行取得上述 28 passed；未修改业务源码或用例断言。
- 原始证据目录：C:/Users/Administrator/AppData/Local/Temp/memoir-pg-b-e331bd328e264d51b051ba248917104f，包含 tests-3.log 与 manifest.json。
- Legacy 升级 fixture / downgrade 专项：NOT RUN；真实 Provider、生产验证与完整 9.6-B 封板不在本轮结论内。
- 本文仅经本会话静态自审；未冒称独立会话合同审查。
