# Part 9.6-B — 专项 PostgreSQL CI 接线合同 V1.0

| Metadata | Value |
| --- | --- |
| Date | 2026-10-14（Asia/Shanghai） |
| Status | SCOPE FROZEN；独立合同审查PASS WITH FINDINGS；六文件实施已获用户批准 |
| Requirement authorization | 用户已批准六项专项 CI 接线要求及先冻结合同的顺序 |
| Implementation | IMPLEMENTED LOCALLY；43项mock检查PASS；独立定向复审PASS，CI-IR-01～04 CLOSED — STATIC；REMOTE CI NOT RUN |
| Baseline | master @ 6c12e96e4f83ada7cb7c7dd60fec4283269f8700，加当前未经提交的9.6-B工作区 |
| Purpose | 解决 B-PC-01：现有 CI 全量 integration 入口不满足 B 分配门禁 |
| Git | 本轮不暂存、不提交、不推送 |
| Release | DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY |

本合同仅新增一次性、专用 B CI 入口；不修改业务实现、既有测试门禁、历史迁移、通用 BM-01 平台或本机 Docker/PostgreSQL。合同归档后，用户批准独立合同审查及通过后的六文件实施；独立合同审查PASS WITH FINDINGS，三项工程澄清已落实。暂存、提交、推送和实际远程验收仍需分别批准。

## 1. 当前缺口与关闭条件

现有 Backend CI：
- PostgreSQL镜像为16.15；
- 固定数据库 ai_life_memoir_test 和 ci_test_user；
- 同一高权限身份执行迁移与全部 pytest -m integration；
- 没有 MEMORY_B_ALLOCATION_RUN_ID / MEMORY_B_ALLOCATED_DATABASE / MEMORY_B_RUNNER_ROLE 等分配信息。

现有 B fixture 必须核验 UUID 命名、数据库/角色对应、SQL version=160015、Runner无管理权限、exact head=b196f0d47a21。不得仅补环境变量、伪造分配收据或跳过权限检查。

B-PC-01 关闭需同时满足：
1. 原入口明确排除 B 文件；
2. 专项 job 确实收集并执行 B 文件全部28个参数化用例及5个双连接用例；
3. 分配、迁移、权限、测试、post-check、精确清理与证据保存全部成功；
4. 后续对包含修复的 exact commit 实际远程执行成功。
静态合同或本地脚本模拟通过，不自动关闭远程 CI Finding。

## 2. Workflow 结构

保持现有 name: Backend CI、push/pull_request 触发、原 backend job 的环境与其他测试职责。

新增 job：
- ID: memory-workflow-postgres
- Display name: B PostgreSQL 16.15
- runs-on: ubuntu-latest
- Python: 3.12，沿用现有依赖安装方式
- 自己的 service ID: postgres，image: postgres:16.15
- 新service的POSTGRES_USER固定为ci_b_bootstrap，POSTGRES_DB=postgres；bootstrap密码只通过该CI service及Manager步骤环境配置，不使用本机/生产凭据，不进入Runner环境或日志。
- 不与原 backend job 共享服务、数据库、角色或可变fixture；
- 两个job独立运行，不用路径过滤、continue-on-error、故意skip或needs造成B job静默遗漏；
- workflow使用普通pull_request，不改成pull_request_target，不使用生产Secret；
- 原已有workflow权限不扩张，checkout不持久化Git凭据至Runner子进程；
- job硬上限15分钟；脚本预检/分配每阶段60秒、迁移每进程180秒、测试180秒、清理60秒；超时不是退出证据。

GitHub为service创建独立容器，并在job结束后销毁；主机job通过映射端口访问。使用 job.services.postgres.id / job.services.postgres.ports[5432] 提供的实际ID与端口，不猜容器名或Windows55432。[GitHub service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/use-docker-service-containers)

GitHub-hosted job运行在独立runner环境；本合同不授权把它移到共享self-hosted生产机器。[GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)

### 2.1 原 backend job 的精确选择

在 apps/backend 工作目录：

    python -m pytest -m integration --ignore=tests/integration/test_memory_workflow.py

只排除这个文件，其余既有integration选择保持原状。SQLite fast、Ruff/format、fresh upgrade、current/check及post-check仍运行；新增CI脚本须纳入lint/format检查。

此排除必须与专项job接线一起交付。不能先只排除文件使CI“变绿”。

### 2.2 专项执行

Manager启动受限Runner，在 apps/backend 工作目录执行：

    python -m pytest -m integration tests/integration/test_memory_workflow.py -q -p no:cacheprovider --junitxml=<本次唯一证据目录>/b-postgres.xml

加载项目已有conftest与models_import，不替换业务fixture、SQL断言或Provider；不是复用本机临时HTTP启动器。

Manager解析JUnit，核验：
- collected/tests=28；
- failed=0、errors=0、skipped=0；
- 双连接Candidate审批1项；
- Memoir/proof/body两种提交顺序4项；
- 每个关键node ID唯一出现；零收集、缺项、异常重复或未来数量变化均失败，先审查合同再调整数字。

MEMORY_B_MULTI_CONNECTION_RUN_ID 必须与本次分配UUID完全一致。不能跳过并发用例后宣布通过。

## 3. 文件白名单

下一轮获批准后的实施候选范围仅6文件：

| 操作 | 路径 | 允许内容 |
| --- | --- | --- |
| Modify | .github/workflows/backend-ci.yml | 原入口精确排除B；新增专用job、script lint和脱敏证据上传 |
| Add | scripts/ci/run_memory_workflow_postgres.py | 一次性Manager、固定Runner子进程、身份/权限核验、结果/清理证据；无通用平台 |
| Modify | 本合同文档 | 实施与审查状态、实际证据；不改业务政策 |
| Modify | README.md | B-PC-01接线状态/验证边界摘要 |
| Modify | docs/05_开发阶段记录/Part开发路线图_V2.0.md | 当前阶段与后续门禁 |
| Modify | docs/00_项目管理/AI人生回忆录平台_开发日志_V1.0.md | 实际实施、验证和清理记录 |

本合同实际路径：docs/05_开发阶段记录/Part9.6-B_PostgreSQL-CI-Wiring_Implementation-Contract_V1.0.md。

不得修改 apps/backend/app/、services/ai-service/、apps/backend/tests/、任何migration、dependencies/config、AGENTS、通用test_support/、scripts/test-postgres/或infra/test-postgres/。若必须扩展范围，先报告具体必要性，重新批准。

本轮归档只有本合同1文件；前述50路径提交候选不自动扩为新白名单，未来须重新审计实际union及混合hunks。

## 4. 资源与身份模型

### 4.1 可信 Manager

- 只在专用job的专属service上激活。核验service ID、镜像、实际port、SQL version() / server_version_num=160015、system_identifier。
- Manager使用新CI service的bootstrap身份；bootstrap具有管理能力，仅Manager持有凭据。
- CI bootstrap不能使用本机 c3_test_user、历史库、已有.env、生产数据库URL。
- 一次UUID v4分配：
  - Database: ai_memoir_b_ci_test_<uuidhex>
  - Owner: b_ci_owner_<uuidhex>
  - Runner: b_ci_runner_<uuidhex>
- 名称必须合法SQL identifier；逐一确认不存在，碰撞立即失败，不认领已有资源。
- Owner为新NOLOGIN、无SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS的专用角色。
- Manager迁移期间临时启用Owner LOGIN及随机密码，仅连接本次库；Runner启动前NOLOGIN且密码清空，确认无Owner会话。
- 数据库TEMPLATE template0、Owner为新Owner；在自己的库写唯一run marker。
- 分配收据记录实际数据库/角色OID、Owner关系、marker、system_identifier；CREATE DATABASE使用autocommit，不声称可由事务回滚。
- Manager以保留的管理连接持有session advisory lock覆盖分配至清理；锁协调本脚本，不防御其他超级用户。

### 4.2 受限 Runner

Runner:
- LOGIN，随机一次性凭据；
- 无SUPERUSER、CREATEDB、CREATEROLE、REPLICATION、BYPASSRLS，未加入其他角色；
- 不拥有数据库/Schema/表，不获得数据库CREATE/TEMP、Schema CREATE或清理权限；
- 仅本次库CONNECT、public Schema USAGE、所需表SELECT/INSERT/UPDATE/DELETE与序列USAGE；
- 不运行迁移，不创建/删除数据库或角色，不执行TRUNCATE；
- 仅在本次库运行原始合成测试，各例回滚；双连接用例使用各自新UUID的已提交图，不复用其他案例的可变数据。

### 4.3 专属CI集群的连接隔离

CI新service与Windows历史容器是不同资源。本合同不使用本机HBA专项规则，不修改任何本机资源。

在这个新CI专属集群：
- 撤销PUBLIC对postgres/template0/template1的CONNECT及临时权限；
- 新临时库撤销PUBLIC权限，仅授予Owner/Runner必要CONNECT；
- 若检查发现其他可连接数据库，Runner对其也须无CONNECT；不能按前缀删除未知库；
- bootstrap Manager仍凭其管理权限管理control数据库；
- 不更改template内容/结构，不启用template0连接，不修改HBA，不clone历史业务库；
- 实际用Runner验证：临时库可连接，control/template1等非分配数据库被数据库权限拒绝；记录拒绝SQLSTATE，不把错误密码、网络超时当隔离成功。
- 建连失败的OperationalError可能无SQLSTATE：只保存实际可用值，缺失记录NULL，禁止由错误文本补造。实际拒绝须结合Manager核验的CONNECT=false、同一Runner凭据的临时库正向连接及数据库权限拒绝类别证据；密码错误/超时仍不通过。

上述ACL变更仅限本次CI job全新专属service；不得在本机或共享集群运行此逻辑。专属资源核验失败STOP。

## 5. 迁移、当前结构与Runner分配数据

Manager按照固定链执行：
1. 核验唯一源码head为 b196f0d47a21、parent为 a196e4c72b08；
2. Owner权限在精确本次库执行 alembic upgrade b196f0d47a21；
3. alembic current/check；
4. 核验4个工作流表及实际head；
5. 关闭Owner LOGIN、授予受限Runner数据权限；
6. 新Runner连接核验version/database/role/privileges；
7. 启动Runner测试；
8. Manager以受限目录读取权限运行独立post-current/check；Runner测试进程本身不运行Alembic；
   post-check进程的SQL身份固定为本次Runner；不重新启用Owner LOGIN，不下发bootstrap密码。
9. 退出/会话核验后精确清理。

不得CREATE_ALL代替Alembic。未来新增migration时应另行更新本合同和固定head预期。

Runner配置：
- TEST_DATABASE_URL = 本次受限Runner精确URL；
- DATABASE_URL若应用初始化需要，仅使用相同Runner目标；
- TEST_MIGRATION_MODE=1；
- MEMORY_B_ALLOCATION_RUN_ID = str(UUID)；
- MEMORY_B_ALLOCATED_DATABASE = 实际分配库；
- MEMORY_B_RUNNER_ROLE = 实际Runner角色；
- MEMORY_B_MULTI_CONNECTION_RUN_ID = str(UUID)。

分配变量必须来自可信Manager核验结果，不从PR请求参数、测试输入或硬编码“假收据”生成。

## 6. 凭据与进程边界

- Manager和Runner是不同SQL身份、不同原生进程。
- Runner没有Manager/Owner密码、bootstrap URL、GitHub token、Docker控制配置或生产Secret。
- Manager持有句柄；Runner使用固定解释器和固定脚本/pytest参数，不使用shell拼接请求载荷。
- Owner迁移子进程只收到Owner的本次库权限；bootstrap权限不下发。
- 凭据用内存或受保护临时配置传入；不写argv、Git、GITHUB_ENV、非敏感manifest或上传artifact。
- 使用清洗环境：固定必要系统PATH/LANG/TMP、合成JWT及本次数据库/分配变量；不继承整份CI环境或任意PYTHONPATH/PYTEST_ADDOPTS/数据库变量。
- 凭据文件位于唯一临时目录，目录0700、文件0600；确认退出后删除。
- 原生进程结果必须确认退出码、EOF、线程/子进程结束；超时或异常不包装为成功。
- 这不是对同一OS下恶意Python的强隔离：固定源码测试不具备防御恶意PR脚本的保证。PR job不得接触生产凭据；不把清洗环境声称为OS sandbox。
- 该脚本明确拒绝普通本机默认执行；CI身份标记只是辅助证据，不能单独授权管理任意数据库。
- 任何数据库连接或ACL变更前，先核验GitHub专属job上下文、实际Docker service ID/镜像/端口绑定，再关联核验SQL版本/集群与bootstrap身份；缺项立即拒绝，无任意URL或本机地址fallback。

GitHubmask仅作为补充，不能替代不输出密码。[GitHub workflow commands](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands)

## 7. 失败与清理状态机

    PLANNED -> ALLOCATED -> MIGRATED -> RUNNING -> POST_CHECKED -> CLEANING -> CLEANED
                     \-----------------------> FAILED / RETAINED

结果分开：
- test_result: passed/failed/not_run；
- migration_result / post_check_result；
- cleanup_result: verified/failed/not_attempted/unknown；
- overall: PASS 仅当必需步骤全部成功且cleanup=verified。

规则：
- 测试失败但退出已确认：仍清理精确本次资源，job失败；
- 测试超时、取消、子进程/线程退出不确定：停止主动数据库清理，留下非敏感manifest，job失败/取消；
- 不任意kill、不DROP DATABASE FORCE、不prefix cleanup、不清理其他run；
- 清理前重新核验service/cluster、库名/OID、Owner OID、marker；
- 确认所有相关子进程已结束、本次数据库无活动会话；随后关闭新连接再普通DROP精确本次库；
- 证明库不存在后删除精确本次新角色并核验不存在；
- 额外依赖、身份变化或DDL结果不确定立即保留；不给出假cleanup PASS；
- 清理失败不能被pytest成功或原backend成功覆盖；
- 不使用独立always清理步骤绕过原Manager的退出/身份条件；Manager内部负责生命周期。

### 7.1 GitHub平台回收边界

job取消/机器丢失时无法保证清理代码或artifact上传执行；GitHub可能按service生命周期自动销毁容器。平台自动销毁不等于Manager已核验数据库清理成功。

退出不确定时，脚本不继续主动DROP，资源在仍存活的job中保留。job最终被平台回收之后，报告为“平台回收/Manager cleanup UNKNOWN”，不能宣称可无限期保留临时CI资源，也不能把取消/证据缺失视为PASS。平台行为见第2节官方service文档。

本条不改变本机未知资源保留规则；旧v3仍UNKNOWN。

## 8. 非敏感证据

每个唯一run生成：
- manifest.json：commit、GitHub run_id/run_attempt/job、UUID、service ID、image ID、SQL版本、system_identifier、库/角色OID、stage状态、native PID/start/exit、cleanup结果；
- b-postgres.xml：完整JUnit结果与5个并发node IDs；
- current/check摘要、pytest脱敏结果及固定错误类别；
- 本次运行源文件SHA，固定migration revision/parent；
- 清理后数据库与角色不存在证据。

仅上传上述明确allowlist；不上传工作目录、.env、connection.json、密码配置、完整docker inspect Env或任意stderr目录。

上传步骤使用always语义，证据目录未创建/证据丢失不能成功；上传失败为CI失败。取消时always不是绝对执行保证，参见7.1。上传action版本与现有仓库/官方兼容版本在实施时固定，不本轮安装插件或改变依赖。

公开CI日志中不展开SQL参数、密码、完整URL或异常repr；synthetic也尽量只记录必要类别。GitHub日志command注入须避免：不要把未净化pytest文本当作workflow命令解释。

## 9. 验收矩阵与后续门禁

| ID | 验收 |
| --- | --- |
| CI-B01 | 原integration仅排除精确B文件，其他测试仍被选择 |
| CI-B02 | 专项job必跑，无path-filter/continue-on-error漏跑 |
| CI-B03 | SQL16.15与service实际身份匹配；错误实例/版本拒绝 |
| CI-B04 | 每run新UUID，碰撞/不明创建结果拒绝自动认领 |
| CI-B05 | Owner/Runner真实角色与权限核验，Runner不是库Owner |
| CI-B06 | Runner能连本次库，其他库拒绝连接；错误密码/超时不是证明 |
| CI-B07 | 迁移exact head、pre/post current/check成功 |
| CI-B08 | 配置来自真实分配；无bootstrap/Owner凭据进入Runner |
| CI-B09 | JUnit28项通过，5个双连接case均执行且无skip |
| CI-B10 | pytest失败仍在确认退出后精确清理，并返回失败 |
| CI-B11 | 超时/取消/退出未知不主动DROP、不假报清理成功 |
| CI-B12 | 库/角色不存在核验；清理失败使job失败 |
| CI-B13 | artifact脱敏allowlist、上传失败/缺证据不PASS |
| CI-B14 | 业务代码、测试门禁、历史migration、BM-01及本机资源未变 |
| CI-B15 | exact commit的backend和B专项实际remote CI均成功 |

实际本地验证：专项脚本32项纯mock合同检查、Ruff/format及workflow YAML/接线断言通过；Windows本机默认激活按预检被拒绝，未调用Docker/PG。CI-B01/02的静态接线及CI-B14的本地文件范围已核对；真实SQL权限/迁移/28项用例/清理/上传和CI-B15远程门禁未在新job执行。随后先独立实现只读复审，再另行批准精确暂存、commit、push及exact-commit remote CI。不得声称Windows本机运行等同GitHub/Linux成功。

需要CI参数错误路径的合成离线检查时，仅在专项脚本内提供测试入口或临时测试载体；不新增通用平台或修改现有测试门禁。

E-01保持OPEN：这个job只接线既有28项，不自动新增B32/B33/B52及所有downgrade分支，不关闭真实Provider/Consent/C6/生产验收限制。

CI job在workflow中必跑，不等于GitHub分支保护已设为required check；仓库管理员的required-check配置若需要调整，属于单独授权的外部配置操作，本任务不修改它。

## 10. 冻结结论

已冻结：job职责、测试分流、版本、角色权限、精确资源分配、迁移次序、JUnit必跑判定、失败/取消策略、清理证据及6文件实施候选范围。

无待定产品数据权限、删除或保留政策被本合同代替；本任务不拍生产retention参数，也不更改现有已确认决策。

**B CI WIRING SCOPE FROZEN**
**IMPLEMENTED LOCALLY — TARGETED IMPLEMENTATION RE-REVIEW PASS / REMOTE CI NOT RUN**

独立合同审查由「9.6-A Review」完成，PASS WITH FINDINGS；并非独立实现审查。B-PC-01为REMEDIATION IMPLEMENTED / OPEN PENDING REVIEW AND REMOTE CI，只有实际接线审查与exact-commit remote验收后才关闭。

实现只增加workflow分流、独立B job和scripts/ci/run_memory_workflow_postgres.py，docs同步限本合同、README、路线图和开发日志。actions/upload-artifact@v4的if-no-files-found=error与明确3文件allowlist按[官方v4文档](https://github.com/actions/upload-artifact/tree/v4)固定；不设置新的生产retention期限。专用脚本不是通用BM-01启动器，也不支持本机默认资源分配。

2026-10-14 独立实现初审FAIL：CI-IR-01～03为Blocking Medium（启动后异常退出证据、权限SQL不确定结果、共享阶段截止），CI-IR-04为Low（post-check失败覆盖测试结果）。定向修复仍在原六文件范围：启动前关闭清理许可、保留原Popen对象并由cleanup复核全部进程；Runner准备异常统一保留；阶段单调截止与剩余预算用于native wait、connect timeout和SQL timeout；已通过test_result与post_check_result分开。43项纯mock检查包含对应故障注入；Ruff/format、YAML接线与本机拒绝复验通过后送定向再审，不能提前宣称finding已关闭。

2026-10-14 独立定向复审完成：PASS，仅限CI-IR-01～04源码修复范围；四项CLOSED — STATIC，6文件初末hash一致，未发现定向范围内剩余实质阻塞。复审未重跑检查；43项mock/Ruff/format为实施者执行证据。新job真实Linux/PG/Remote CI仍NOT RUN，B-PC-01继续OPEN；E-01与全57项未验收、三份文档混合hunks仍保留。下一步重新审计原50路径与新增workflow/脚本/本合同组成的53路径候选union，仍须用户单独批准暂存/提交/推送。
