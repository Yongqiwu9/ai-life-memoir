# AI人生回忆录平台 — Part 开发路线图 V2.0

## 当前 9.6-B 封板文档准备（2026-10-15）

- Implementation Completed / Validation Passed：仅已确认的离线/合成/指定PG范围。Final Documentation Seal仍为PREPARATION，文档尚未提交/推送或取得对应CI，不写Completed/Sealed。
- 实现基线master @ e164c521e2ac5ed5aba992a327ae8e34b94bf00f已推送；Backend CI38617553685双job completed/success，远程Fast642、普通PG48、B专项PG16.15 45项／竞争11／0skip、迁移及清理verified。
- 57项逐项归档：54行约定层执行＋B38用户确认范围＋B46静态inventory＋B48执行和约束证明；不按套件数量相加或称每条所有层验证。原审查人E-01定向复核PASS，B范围证据缺口CLOSED；原初审历史不改写。
- 保留真实Provider、生产Consent/C4/C6、同旧Memory恢复、备份/第三方传播、生产回退/部署未完成边界及旧v3 UNKNOWN。AI58、Legacy18是历史执行，最新Backend CI未重跑；本地Fast920含未提交C3，不是远程642。
- 当前仅Documentation Only封板准备；下一步「Git Commit Review」只读文档审计→分别授权暂存/提交/推送→文档exact-commit CI→正式封板状态确认。不开始下一阶段，不把阶段验收当生产可用或BM-01 CLOSED。
- 详细SSOT：[B01–B57对账](Part9.6-B_B01-B57_Acceptance-Reconciliation_2026-10-15.md)、[E-01独立关闭意见](Part9.6-B_E01_Coverage-Closure_Independent-Review_2026-10-15.md)；下方记录按历史时点保留。

## 补验前实施记录（历史快照）

以下旧 HEAD、未提交/未执行和待复审状态均对应补验前时点，不覆盖上述当前摘要；不改写既有 C3/BM-01 历史。

> 最新B CI结论（2026-10-14）：六文件专项接线已实施，独立定向源码复审PASS，CI-IR-01～04 CLOSED — STATIC；43项mock、script Ruff/format、YAML检查PASS。真实Linux/PG/remote双job未运行，B-PC-01和E-01保持OPEN。下一门禁是53路径候选union的定向Pre-Commit Audit与三份混合文档hunk核验，然后由用户分别批准暂存/提交/推送。旧待再审条目为历史记录，不表示当前源码阻塞仍未修复。

> B CI修复最新状态（2026-10-14）：独立实现初审FAIL，CI-IR-01～04已作六文件范围内定向修复；43项纯mock检查含启动后IO/通信/超时/残留group、权限准备不确定、共享阶段预算及post-check结果独立记录。待独立定向再审；新job真实Linux/PostgreSQL/Remote CI仍未运行。后文32项及“实现复审待完成”保留首次实施历史，不能替代本次再审结论。

> B CI 最新接线状态（2026-10-14）：六文件实施已获用户批准并写入工作区；原入口精确排除B文件，新增独立PostgreSQL16.15 job及专项Manager/Runner脚本。独立合同审查PASS WITH FINDINGS；32项mock合同检查、脚本Ruff/format、YAML接线检查通过，本机激活被预检拒绝，无Docker/PG操作。独立实现复审待完成，新job实际Linux/PG/remote CI尚未运行，B-PC-01保持OPEN；E-01、B32/B33/B52等覆盖缺口不被新job自动关闭。下一步：独立实现复审→重新Pre-Commit Audit→分别批准暂存/提交/推送→exact-commit双job验收。详细SSOT见[CI接线合同](Part9.6-B_PostgreSQL-CI-Wiring_Implementation-Contract_V1.0.md)。

> 最新主线状态（2026-10-14）：HEAD 仍为 `6c12e96e4f83ada7cb7c7dd60fec4283269f8700`。9.6-B 的 42 文件离线实施已获授权并写入工作区，独立实现复核 PASS WITH FINDINGS，B-IR-01～04 CLOSED。合成 HTTP 15 项、PG16.15 28 项、Legacy/downgrade 18 个脚本场景在各自范围通过，清理核验通过；57 项逐项验收未全部完成，B32/B33/B52 指定 PG 并发证据仍缺。下一步为文档同步后的只读 Pre-Commit Audit；未暂存、未提交、未推送、未封板。9.6-A 的专项 HTTP/PG 未验证边界不被 B 的结果代替；Real Provider、真实 Consent/C6 仍未实现。下方历史阶段记录不代表最新主线状态。

## Part 9 — Backend Core

| Part | 内容 | 状态 | 关键交付 |
| --- | --- | --- | --- |
| 9.1 | Backend Infrastructure | 基础实现完成 | FastAPI、SQLAlchemy、Settings、Logging、Exception、Alembic、pytest、ruff |
| 9.2 | User + JWT Authentication | 基础实现完成 | User 模型、bcrypt、JWT、注册/登录/当前用户 |
| 9.3 | Family + FamilyMember | 数据模型/API 完成 | 家庭与档案人物 CRUD、当前 Owner-only isolation |
| 9.4 | Interview | 数据模型/API 完成 | Interview / InterviewSession / InterviewMessage、当前所有权查询链；状态机仍待决策与落地 |
| 9.5 | Audio/STT 数据基础设施 | 数据模型/API 完成 | AudioRecording / Transcript / TranscriptSegment 元数据、Message source/segment 扩展 |
| 9.5.5 | Memory 前置基础设施/架构决策 | C Design Frozen；Implementation In Progress | B、C1/C2A/C2B、C3.0 Completed / Sealed；C3.1 Implementation Audit = PASS WITH FINDINGS，本地 PostgreSQL 16.15 与回归验证 PASS，Implementation Completed（dormant scope），commit / push / exact remote CI PASS；Final Documentation Seal pending；C3.2 Next / NOT STARTED |
| 9.6 | Memory Extraction | Planned（规划中） | MemoryCandidate / Memory、提取与人工确认流程，尚未实现 |
| 9.7 | AI Agent | 规划中 | 访谈追问、assistant 消息生成 |
| 9.8 | Memoir Generation | 规划中 | Memory → Memoir 组装与编辑 |

Part 9.1–9.5 的完成范围是基础 Backend、数据模型与 API。Part 9.5 不代表 Audio upload、Object Storage、STT Provider 或 AI pipeline 已完成；当前尚无真实录音到转写的自动处理链路。

Part 9.5.5-A 是文档决策整理任务，未创建模型、状态转换、迁移、CI 或 AI/STT 功能。当前 ADR-001、003、004、005、006 为 Accepted；ADR-002、007 为 Proposed；ADR-008、009 仍为 Proposed，其中部分合同由 9.5.5-C 冻结。ADR 状态与 Design Frozen 均不代表功能已经实现，也不代表 Part 9.6 已开始开发。

Part 9.5.5-B 保留现有 SQLite 快速测试，增加标记为 `integration` 的 PostgreSQL 测试、共用的 `TEST_DATABASE_URL` 加载与校验、以及 GitHub Actions Backend CI。进程环境变量优先，本地可读取 Git 忽略的 `apps/backend/.env.test`。测试迁移必须显式设置 `TEST_MIGRATION_MODE=1`；缺少安全的测试 URL 时立即失败，不回退到开发库。普通 Alembic 迁移仍使用原有 `DATABASE_URL`。CI 使用临时 PostgreSQL service，并通过环境变量提供测试 URL 和测试迁移模式。本地真实 PostgreSQL 和远程 GitHub Actions 均验证通过。

项目 PostgreSQL 基线为 **PostgreSQL 16.x**，当前本地集成测试与 GitHub Actions 均在 **16.15** 上验收。其他 major 版本不作为本项目的权威集成测试数据库；major 升级必须另行完成兼容性验证。

2026-10-05 Part 9.5.5-B 最终验收完成：专用 PostgreSQL 18.6 测试库空 public schema 成功迁移至唯一 head `adf9c60d178d`，current/check 及集成测试后的 current/check 均通过。Ruff/format 通过；SQLite fast tests：94 passed / 0 failed / 0 skipped / 2 deselected；PostgreSQL integration tests：2 passed / 0 failed / 0 skipped / 94 deselected。Local validation: PASS；Remote CI: VERIFIED / PASS。Implementation commit: `07d1f51699b9fbcdaa09b2652be23d3349948921`；[Backend CI run 37283732708](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37283732708)，master，completed / success。

Current Part: Part 9.5.5-C3.1 SourceArtifact Registry Schema / Models — Implementation Audit = PASS WITH FINDINGS；本地 PostgreSQL 16.15 与回归验证 PASS；Staged Audit / Exact Commit Audit / Push / Remote Backend CI 均 PASS；Implementation Completed（dormant scope）。Final Documentation Seal Preparation in progress，独立封板提交及其自身 exact-SHA CI 未完成。C 与 C3 整体 Implementation In Progress。设计以 [父级 Design Freeze](../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md) 与 [C3 Addendum](../03_业务流程/Part9.5.5-C3_Implementation-Contract-Addendum_V1.0.md) 为准。C1/C2A/C2B、C3.0 Completed / Sealed；C3.2 Content Artifact Integration — Next；Part 9.6 Planned / NOT STARTED。

C3.0 evidence：Addendum commit `345f852d36f94752ddea99fba1f889d9d632ded0` / [CI 37762742776](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37762742776)，及封板 commit `5f09d6c7e4c57672a85cca548cda150bc3c39c30` / [exact CI 37765330926](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37765330926) 均 completed / success；Final Contract Re-Audit PASS，BM-01～04 CLOSED，C3.0 已封板。这些运行验证 pre-C3 基线，不证明 C3.1 功能。

C3.1：SourceArtifact 模块未加入生产 metadata，未新增 migration。2026-10-09 PostgreSQL 16.15 本地验证通过：原型 8 passed；完整 integration 48 passed / 180 deselected；SQLite fast 180 passed / 48 deselected（含原型 7 passed）；均为 0 failed / 0 errors / 0 skipped。Ruff/format 与 Alembic heads/current/check PASS，单 head `d4f8a1c2b3e6`。Implementation Audit = PASS WITH FINDINGS；Staged Audit / Exact Commit Audit / Push / Remote Backend CI 均 PASS；独立文档封板提交及其自身 CI 尚未完成。C3-A/C3-B 未创建、未部署；无 runtime Registry、live content artifact_id、最终 PostgreSQL guards 或 Consent / Access Gate；部分 C3 不得独立生产发布。

C3.1 implementation commit：`aa711f9b2b18ad522226b1d99afac47ea0a0dc3e`；[Backend CI run 37939418187](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37939418187)，workflow `.github/workflows/backend-ci.yml`，event push，branch master，head SHA 与 implementation commit 精确匹配，completed / success。远程 SQLite 180 passed / 48 deselected，PostgreSQL integration 48 passed / 180 deselected，均 0 failed / 0 skipped；PostgreSQL 16.15；Ruff、format（128 files）、Alembic heads / fresh upgrade / current / check / post-integration current/check PASS，单 head `d4f8a1c2b3e6`。

C3.1 仅在批准的 dormant SourceArtifact ORM foundation 范围内 Implementation Completed，不代表生产部署或完整 C3 完成。Production metadata registration、runtime Registry、content artifact_id integration、historical backfill、DerivedSource DAG、SourceSpeakerBinding、ArtifactContribution、final PostgreSQL source guards、Consent / Access Gate 和 production deletion pipeline 均 NOT IMPLEMENTED；C3-A/C3-B 均 NOT CREATED。C2B、C3.0 保持 Completed / Sealed，既有 Owner-only 内容 API 权限不变。DF-01：Deferred Medium，单语句 Family multi-path DELETE 可触发 SQLSTATE 23503，归属 C6 deletion flow / later C3 guards；L-01：Low，Starlette/httpx 弃用警告，归属 Backend dependency maintenance。

Final Documentation Seal：Preparation in progress。独立文档封板 commit 及其自身 exact-SHA Backend CI 尚未完成；仅在该提交推送且其 exact-SHA CI completed / success 后最终封板才生效。当前不声明 C3.1 Sealed，不预填未来 seal SHA 或 CI Run ID。C3.2 Content Artifact Integration — Next / NOT STARTED；Part 9.6 — Planned / NOT STARTED。

C3.1 FK 验证仅证明测试用终态 fixture 中逐项 Session / Interview / Family 删除的 SET NULL 与稳定 scope 保留；不授权普通 live-state 删除。PostgreSQL 16.15 的单条 Family 多路径 cascade 已复现 SQLSTATE 23503，此机械限制仍需在后续合法删除流程设计中处理；本阶段未实施该流程或最终反向保护。

### Part 9.5.5-C 实施子阶段

| 子阶段 | 范围 | 状态 |
| --- | --- | --- |
| C1 | Policy + Identity Foundation | Completed / Sealed |
| C2A | FamilyMembership + Invitation + Durable Idempotency | Completed / Sealed |
| C2B | InterviewParticipant + participant_confirmation | Completed / Sealed |
| C3 | Artifact Registry + Provenance | Implementation In Progress |
| C3.0 | Implementation Contract | Completed / Sealed |
| C3.1 | Registry Schema / Models | Implementation Audit = PASS WITH FINDINGS；Implementation Completed（dormant scope）；本地验证 / Staged Audit / Exact Commit Audit / Push / Remote Backend CI PASS；Final Documentation Seal pending separate commit and exact-SHA CI |
| C3.2 | Content Artifact Integration | Next / NOT STARTED |
| C4 | Consent + Source Binding + Access Gate | Planned |
| C5 | RevisionProposal | Planned |
| C6 | Deletion + Ledger + Outbox | Planned |
| C7 | Restore + Expiry + Sanitization | Planned |
| C8 | PostgreSQL Integration + Security Final Audit | Planned |

C1 evidence：implementation commit `35ec7e33a060b07e4834091b04c2caeb852b707c`；[Backend CI run 37412935434](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37412935434)，completed / success。

C2A evidence：implementation commit `a33f6eb6160a2e0eb5276b0c08d9a5d9c2534cfd`；migration `b7e2c4d891a0`；[Backend CI run 37492358055](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37492358055)，completed / success；Fast 163 passed / 29 deselected；PostgreSQL integration 29 passed / 163 deselected。

C2B evidence：implementation commit `1038313cd57f6a76f5c6c27213912284e5af38fa`；remediation commit `fbb79b6a8af06b3d50e1d4923eb56169128efcde`；migration `d4f8a1c2b3e6`；[Backend CI run 37627066699](https://github.com/Yongqiwu9/ai-life-memoir/actions/runs/37627066699)，master，completed / success，PostgreSQL 16.15；targeted 3 passed；C2B PostgreSQL 11 passed；Fast 173 passed / 40 deselected；完整 PostgreSQL integration 40 passed / 173 deselected；Ruff、format、Alembic 全部 PASS。

决策明细见 [Part 9.5.5-C Final Implementation Design Freeze](<../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md>)；ADR 总览见[系统架构总览的 ADR 状态表](../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md#7-memory-前置决策边界)。

## 后续阶段（概览）

- Part 10：老人端 UniApp（elder-app）
- Part 11：管理/写作后台（writer-admin）
- Part 12：AI Service 独立化、RAG/Embedding
- Part 13：部署与运维（infra）

## 阶段原则

1. 每个 Part 只做最小增量，禁止提前实现后续模块。
2. C2A 仅向邀请和 Membership 管理开放 Owner / active Collaborator 权限；C2B 仅增加 Participant proposal 与本人最小身份操作。既有档案内容 API 继续执行 Owner-only isolation；Consent 及内容级协作者访问尚未实现。
3. 数据库变更必须走 Alembic，保持单一 head。
4. 每个 Part 完成必须通过 pytest / ruff / alembic check / PostgreSQL smoke。
5. 每个 Part 独立 commit，保留历史审计轨迹。

Part 9.5.5-C Design Freeze 文档保留设计封板时的历史快照。C1 已实现并封板 Policy / Identity Foundation。C2A 已实现并封板 FamilyMembership、FamilyInvitation、持久化命令幂等、邀请身份核验和协作管理 API；Membership 不授予既有档案内容访问权。C2B 已实现并封板 InterviewParticipant、`participant_confirmation`、本人确认/停用和最小本人读取；Participant verified 不等于 Consent，Participant relationship 不授予档案内容访问权，既有内容 API 继续保持 Owner-only。Consent、来源、修订、删除和净化业务仍未实现。生产加密/投递/密钥管理/限流能力未接入时，验证入口保持关闭；生产 retention 值尚未冻结。Part 9.5.5-C 与 C3 整体 Implementation In Progress；C3.0 Completed / Sealed；C3.1 Implementation Audit = PASS WITH FINDINGS，本地 PostgreSQL 16.15 与回归验证 PASS，Implementation Completed（dormant scope），commit / push / exact remote CI PASS；Final Documentation Seal pending；C3.2 Next / NOT STARTED；C4 Consent + Access Gate 后续实施；Part 9.6 Planned / NOT STARTED。


## Memory + Memoir MVP Vertical Slice 1（2026-10-11）

> 历史实施与验证记录保留如下；当前结论以本节末“最新核验状态同步”为准。

本节更新当前业务开发主线；前述 C3/BM-01 历史记录与已有编辑保留。当前阶段：Memory + Memoir Slice 1 代码完成 / SQLite 验证通过 / PostgreSQL 验证待执行。C3 不因此完成或启用。

- 已实现：Owner-only 人工结构化 Memory 创建、读取、分页列表、更新；每条 Memory 固定关联一个同一 FamilyMember 的原始 InterviewMessage。保留时间原话、地点、情感，不改写 Message / Segment。
- 已实现：同一 FamilyMember 的选定 Memory 按请求顺序确定性组装 Memoir draft；保存 MemoirSection 标题/正文快照、position 与 memory_id；可读取草稿及有序章节。Memory 后续更新不会覆盖已有章节。
- API：POST/GET /api/v1/family-members/{member_id}/memories；GET/PATCH /api/v1/memories/{id}；POST /api/v1/family-members/{member_id}/memoirs；GET /api/v1/memoirs/{id}；GET /api/v1/memoirs/{id}/sections。复用 JWT 与既有 Owner-only 权限，不开放协作者内容权限。
- 迁移源码：e8c2a9b47106 -> down_revision d4f8a1c2b3e6；新增 memories / memoirs / memoir_sections。静态解析确认唯一 head e8c2a9b47106；未执行 upgrade/downgrade/current/check，未连接真实 PostgreSQL。
- 本轮实际测试：新增及既有认证/家庭/访谈/消息/音频/转写/健康 API 回归 97 passed；最终新增模块复测 11 passed；Ruff check 与 format --check（14 个相关 Python 文件）PASS；1 条既有 Starlette/httpx 弃用警告。不是全仓测试或 PostgreSQL 验收。
- 测试隔离：每用例独立内存 SQLite、FK 开启，结束后释放；执行进程禁用 dotenv 读取与第三方 pytest 自动插件，拦截所有非内存 SQLite Engine.connect。沙箱内 Windows TestClient socketpair 初始化停滞，诊断进程已退出，两个停滞进程已中断；经执行审批在沙箱外运行相同数据库门禁测试通过。未读取 .env.test，未使用历史数据库。
- 验证分类：SQLite PASS；真实 PostgreSQL NOT RUN / PENDING；真实数据库清理 N/A（未创建资源）；无本任务遗留数据库资源。未操作 Docker、BM-01、Git staging/commit/push。
- 已覆盖：来源追踪、原文保持不变、跨用户/家庭/人物关联拒绝、非法/不存在 ID、认证、统一 404、422/INVALID_SOURCE、分页、章节顺序与快照、Memory/Memoir 写入失败 rollback、来源外键保护。
- 待执行集成验证：在未来专项授权的唯一可丢弃 PostgreSQL 数据库验证迁移/ORM 一致性、FK/CHECK/UNIQUE、事务、删除冲突及并发行为；本任务没有新增 PostgreSQL 用例，不把 SQLite 当作真实 PostgreSQL 证据。
- 限制：仅人工 Memory 和确定性草稿；无 MemoryCandidate/正式审批/版本历史、AI Provider、RAG、writer 编辑、支付或自动 STT。每条 Memory 一个来源；source association 不可更新；章节顺序由创建请求指定，尚无创建后重排 API。
- 限制：引用采用 RESTRICT 保留证据链，已有家庭/人物/访谈删除在存在新引用时可能报外键错误；本任务未改写既有删除 API，应后续补合法删除流程与冲突响应。同人物约束由 Service 实施，尚无跨表 PostgreSQL guard。C3 provenance、C4 Consent/Access Gate 与 C6 删除传播未接入，不宣称生产就绪或本人授权已满足。
- Next MVP：补充 Memory 审查/版本与合法删除冲突契约，再独立验收 PostgreSQL。下一 AI Agent milestone（Part 9.7）：独立 AI Service 接口及访谈追问，输出仅写 assistant/ai_generated Message；须先满足来源/Consent/Provider 门禁，不直接写正式 Memory。本 slice 不表示 Part 9.6 AI Extraction 或 Part 9.7 已上线。



**最新核验状态同步（2026-10-11，依据项目 Owner 提供的独立复审结果）**

- Memory + Memoir MVP Slice 1：Implementation completed；代码实现与安全复审在限定范围内完成。Independent Code Security Gate：PASS within reviewed code scope；该结论不代表 HTTP、PostgreSQL 或生产验收通过。
- Finding decisions：MM-01 CLOSED — code / SQLite scope；MM-01-R01 CLOSED — code / SQLite scope；MM-02 CLOSED — code / offline scope。MM-01-R01 删除入口采用 Owner-scoped Interview 查询，现有他人 ID 与不存在 ID 使用等价的 404 正文；保留 MM-01 引用冲突 409、rollback 与 RESTRICT 保护。
- 最新独立证据：18 passed / 0 failed / 0 skipped / 16 deselected；Independent probes：3 passed。两组证据分别记录，不相加为唯一测试用例数；本次文档同步没有运行测试。
- HTTP API Gate：BLOCKED / NOT RUN。原因：当前沙箱条件阻止所选 ASGI 测试路径的获批执行。历史实施测试与 collect-only 记录保留，不替代当前 HTTP API Gate。
- PostgreSQL migration/integration：NOT RUN；路线图 PostgreSQL integration：PENDING。Concurrency：NOT VERIFIED on real PostgreSQL；SQLite / mock 结果不作为真实 PostgreSQL 验证。
- Remaining findings：MM-03 OPEN — Low — bounded N+1 queries；MM-04 OPEN — Low — test dependency override restoration。两项均未在本轮实现或关闭。
- 当前阶段：Memory + Memoir Slice 1 code implementation and security review completed at limited scope；Git development snapshot：PREPARATION IN PROGRESS；HTTP API validation：BLOCKED。
- Release classification：DEVELOPMENT SNAPSHOT ONLY；NOT PRODUCTION READY。下一主线里程碑：AI Interview Agent MVP；本次不启动后续开发。
- BM-01 remains OPEN and separate；不改变任何无关 C3 milestone 状态或历史结论。Git development snapshot 尚未 staging、commit 或发布，本次文档同步不授权这些操作。

## MM-01 / MM-02 Targeted Remediation（2026-10-11）

> 历史实施与验证记录保留如下；当前结论以本节末“最新核验状态同步”为准。

本节更新 Slice 1 当前状态：定向修复已实现 / 离线 SQLite Service 验证通过 / 独立复审待执行；不自批准封板，不启动下一 Slice。前述记录保留为历史。

- 基线：master，HEAD fb5c384dca15bef16b9ee350d04081ac2f8ceb04；编辑前索引为空，已记录九个拟修改文件 SHA-256。仅修改授权的六个 Service/CRUD 文件、test_memory_memoir.py 及本日志/路线图。
- MM-01：Interview / FamilyMember 删除先完成 Owner 授权，再检查受保护 Memory/Memoir 引用；冲突返回 409 / RESOURCE_IN_USE / 通用脱敏消息。删除 CRUD 只 flush，由 Service commit；flush/commit 失败均 rollback。PostgreSQL 仅识别 SQLSTATE 23503 + 指定保护 FK 名 + 目标表；SQLite 仅识别 FK 错误码/固定错误文本并复核保护引用。其他 IntegrityError 保持原异常，不泛化为 409。未新增 Session/Message 删除接口，未更改 RESTRICT。
- MM-02：Memory/Memoir 改为经 FamilyMember -> Family.owner_id 过滤的查询；GET/PATCH Memory、GET Memoir/sections 的他人及不存在 ID 返回一致资源类型的 NOT_FOUND 正文。正文查询仅命中 Owner 范围；原始来源与跨人物校验保留。
- 实际执行：沙箱内新增离线 Service/CRUD 测试 16 passed / 14 deselected，1 条既有 Starlette/httpx 警告。每例独立内存 SQLite，实测 foreign_keys=ON；dotenv 读取及其他数据库连接被进程门禁禁止，无 TestClient 实例运行。
- 证据分类：SQLite 真实 FK flush 失败及 rollback/data preservation PASS；PostgreSQL SQLSTATE/constraint-name/table-name 分类与 flush/commit 失败仅为模拟验证。覆盖他人/缺失 404 完整 JSON、正常 Owner 读取、跨家庭/人物源拒绝、正常无引用删除、草稿排序/快照/分页及无关 IntegrityError 不误转 409。
- NOT RUN / BLOCKED：40 个 API 用例完成安全 collect-only（含 3 个新增定向 API 用例及既有回归），未执行 TestClient；当前任务禁止绕过沙箱限制，沿用已知 Windows socketpair 阻塞条件，不申请沙箱外运行。真实 PostgreSQL、迁移、并发及生产验收均 NOT RUN / PENDING；无真实资源创建或清理，cleanup N/A。
- MM-03 / MM-04：仍为 Low / 待处理；本任务未提供具体发现正文，不推断内容、不宣称已修复。
- 已知边界：Family DELETE 不在本轮授权内；既有空引用但含 Interview 的 FamilyMember ORM 删除可能发生其他完整性错误，未将其误映射为引用冲突；完整删除/Consent/版本历史仍待后续专项任务。上述两项修复尚待独立复审及 HTTP/真实 PostgreSQL 验证。
- 下一计划里程碑仍为独立 AI Interview/Agent：AI Service 访谈追问、assistant/ai_generated Message；依赖来源/Consent/Provider 门禁。本轮不开始该里程碑，不调用模型。
- Git 安全：未 stage/commit/push/reset/clean；既有 16 个删除、ad、BM-01 文件、其他 Slice 文件和既有文档编辑保留；未读取 .env.test 或 secrets，未连接 PostgreSQL、执行迁移或操作 Docker。

**最新核验状态同步（2026-10-11，依据项目 Owner 提供的独立复审结果）**

- Memory + Memoir MVP Slice 1：Implementation completed；代码实现与安全复审在限定范围内完成。Independent Code Security Gate：PASS within reviewed code scope；该结论不代表 HTTP、PostgreSQL 或生产验收通过。
- Finding decisions：MM-01 CLOSED — code / SQLite scope；MM-01-R01 CLOSED — code / SQLite scope；MM-02 CLOSED — code / offline scope。MM-01-R01 删除入口采用 Owner-scoped Interview 查询，现有他人 ID 与不存在 ID 使用等价的 404 正文；保留 MM-01 引用冲突 409、rollback 与 RESTRICT 保护。
- 最新独立证据：18 passed / 0 failed / 0 skipped / 16 deselected；Independent probes：3 passed。两组证据分别记录，不相加为唯一测试用例数；本次文档同步没有运行测试。
- HTTP API Gate：BLOCKED / NOT RUN。原因：当前沙箱条件阻止所选 ASGI 测试路径的获批执行。历史实施测试与 collect-only 记录保留，不替代当前 HTTP API Gate。
- PostgreSQL migration/integration：NOT RUN；路线图 PostgreSQL integration：PENDING。Concurrency：NOT VERIFIED on real PostgreSQL；SQLite / mock 结果不作为真实 PostgreSQL 验证。
- Remaining findings：MM-03 OPEN — Low — bounded N+1 queries；MM-04 OPEN — Low — test dependency override restoration。两项均未在本轮实现或关闭。
- 当前阶段：Memory + Memoir Slice 1 code implementation and security review completed at limited scope；Git development snapshot：PREPARATION IN PROGRESS；HTTP API validation：BLOCKED。
- Release classification：DEVELOPMENT SNAPSHOT ONLY；NOT PRODUCTION READY。下一主线里程碑：AI Interview Agent MVP；本次不启动后续开发。
- BM-01 remains OPEN and separate；不改变任何无关 C3 milestone 状态或历史结论。Git development snapshot 尚未 staging、commit 或发布，本次文档同步不授权这些操作。

## Part 9.6 — AI Interview / Candidate 交付路线图（2026-10-11，最新阶段状态）

> 本节追加最新已核验的项目实施路线，不回写、不删除早期规划和 C3/BM-01 历史状态。早期“Part 9.6 Memory Extraction / Part 9.7 Interview Agent”是历史规划；本轮项目 Owner 将实际 AI MVP 主线细分为 **9.6-A / 9.6-B / 9.6-C**。该编号调整只作用于最新推进计划，避免把旧记录解释为既往已完成。

| 交付片段 | 实际范围 | 最新状态 | 明确不包含 |
| --- | --- | --- | --- |
| Memory + Memoir Slice 1 | 人工 Memory + 确定性 Memoir 草稿；已推送开发快照 `8421f1d` | Git development snapshot uploaded；HTTP / PostgreSQL 仍待验证 | AI 提取、Consent 实运行、生产发布 |
| **9.6-A** | Mock Agent + M01 修复 + Provider Extension v2；显式 request_question、pause/resume/end、锁外 Provider 边界、幂等与迁移源码 | **Provider Extension Implementation Completed；Contract Compliance / Independent Review PASS；本次审查 Critical/High/Medium/Low 均 0；Documentation Sync Completed；Git staging/commit/push 未授权** | 真实 Provider/Consent、真实 PostgreSQL 验证、HTTP/ASGI 验证、RAG、Candidate |
| **9.6-B** | Candidate Memory、不可变 Revision、原始 Message 证据引用、人工纠正/批准/拒绝、原子创建 Memory | **NEXT — NOT STARTED / 待最小实施范围审批** | 默认自动确认候选、自动覆盖原始答案、真实 Provider |
| **9.6-C** | 获批后的真实 AI Provider 适配、来源许可与撤回/迟到结果控制、跨服务传输 | **FUTURE — NOT STARTED / 依赖 Consent 与 Provider 批准** | 在授权完成前处理真实个人数据 |

**原 9.6-A Mock 交付与证据（历史）**：14 新增 + 5 局部修改；Backend API `GET /api/v1/sessions/{session_id}/agent-state` 与 `POST /api/v1/sessions/{session_id}/agent-turns`；独立 AI Service 契约与规则 Mock；迁移文件 `f3a96b10d207`（parent `e8c2a9b47106`，未执行）；`UNIQUE(session_id, sequence)` 的 PostgreSQL 实际迁移与并发行为尚未验证。默认 `503 / POLICY_UNAVAILABLE`，仅通过合成测试注入许可。M01 因 `SET NULL` 引起的错误重放已经按静态审计关闭，修复后缺失原输出返回 `409 / IDEMPOTENCY_RESULT_UNAVAILABLE`。

**原 Mock / M01 测试证据层级（历史）**：实施者报告 Backend 离线 42 passed、Memory/Memoir 18 passed、AI Mock 10 passed；M01 修复后专项离线 51 passed / exit 0。Codex B 复核了代码、哈希与回归断言，未独立执行测试或取得原始终端输出；不得将这些数据宣传为独立运行证据、Provider Extension 测试数量或全仓通过。HTTP/ASGI NOT RUN；真实 PostgreSQL upgrade/current/check、集成和并发 NOT RUN / NOT VERIFIED。

**仍存在的限制**：`9.6A-L01` Low OPEN（v1 duplicate end semantics issue，历史发现继续独立跟踪；当前 v2 新 key 重复 end 被拒绝，同 key 幂等重放保留）；原有 `MM-03`、`MM-04` Low OPEN，`BM-01` OPEN；C3/C4/C6 的来源、Consent、删除传播能力未完成。9.6-A 尚未 Git stage/commit/push，工作区历史修改、16 个未暂存删除、`ad` 与 C3/BM-01 内容必须保留。`DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY`。

**近期执行顺序**：仅在另行批准的精确范围内完成 9.6-A 文档同步与后续 Git 评审/提交；9.6-B 先只读核对 Candidate / Revision / 审批事务接口，再实施合成数据 Mock；HTTP + SQLite 与获授权的隔离 PostgreSQL 集成继续作为独立验证轨道。9.6-B 不需要等待 BM-01 全面封板才能开展不接触真实个人数据的 Mock 开发。


## Part 9.6-A Provider Extension 合同草案归档（2026-10-12，近期步骤补充）

> 本节保留合同起草时的状态；待审查 / 未实施已由下方最新记录取代。合同正文的起草与工程澄清状态属于历史，不作为最新交付状态。

- 详细草案：[Scope Freeze + Implementation Contract V1.0](../04_AI设计/Part9.6-A_Provider-Extension_Implementation-Contract_V1.0.md)。产品范围已确认；工程合同完整草案待独立审查与批准，**DRAFT — PENDING INDEPENDENT REVIEW / IMPLEMENTATION NOT STARTED**。
- 近期顺序：合同独立审查与批准 → 另行授权的 9.6-A Provider Extension 离线实施 → 9.6-B Candidate + Revision + Human Review → 获批后的 9.6-C 真实 Provider 接入。Provider Extension 属于 9.6-A 后续子阶段，不替换 9.6-B。
- 本次为 Documentation Only 归档，不改变上述既有 Mock 实现、M01 审查及 HTTP / PostgreSQL / 真实 Provider 的证据边界；不代表 Design Frozen、实施授权或验证通过。

## Part 9.6-A Provider Extension — 最新交付与提交门禁（2026-10-12）

> 本节保留上一轮仅同步开发日志与路线图的记录；README、合同及 L01 的后续同步见文末本轮补充。

依据项目 Owner 提供的《Part 9.6-A Provider Extension Independent Review Report》同步；本轮未复现审查或测试，不新增测试计数。详细实施依据仍为 [Provider Extension Contract V1.0](../04_AI设计/Part9.6-A_Provider-Extension_Implementation-Contract_V1.0.md)，该文档保留历史起草记录；首页及 17.4 已同步 IMPLEMENTED / Implementation Review PASS，最新交付状态与本节、文末本轮补充及 [开发日志](../00_项目管理/AI人生回忆录平台_开发日志_V1.0.md) 对照。

| 项目 | 当前状态 |
| --- | --- |
| Provider Extension Implementation | Completed（源码及离线增量范围） |
| Contract Compliance / Independent Code Review | PASS / PASS（源码审查及本轮无数据库验证范围） |
| Critical / High / Medium / Low Finding | 0 / 0 / 0 / 0（仅本次审查范围） |
| 修复要求 | 无 |
| Documentation Sync | Completed |
| Git Commit Readiness Review / Staged Audit | PENDING / NOT RUN |
| Git staging / Commit / Push | 未授权；本轮未执行 |
| HTTP/ASGI 完整请求链 | NOT VERIFIED（沿用 NOT RUN） |
| PostgreSQL Migration / Integration / 并发锁 | NOT VERIFIED；本轮未执行 |
| Real Provider / Consent 真实流程 | NOT IMPLEMENTED / NOT IMPLEMENTED |
| 生产部署 / 真实数据库清理 | NOT STARTED / N/A（本轮未创建资源） |
| 发布分类 | DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY |

- **已形成闭环**：Mock Agent → M01 修复 → Provider Extension Contract → Implementation → Independent Review PASS。Provider v2、可替换 AIProvider、Mock Registry 和预留 / 锁外调用 / 重新校验发布已形成离线源码边界；真实 SDK、模型与跨服务 transport 待后续实施。
- **当前 v2 语义**：`start / request_question / pause / resume / end`；AgentState `idle / listening / paused / ended`。request_question 发布后仍为 listening，pending 属于 Turn；pause 允许保存文字，resume 不补问题，end 完成 Session 而非 Interview，Session 完成后拒绝新 Message。legacy awaiting_answer 与 Session completed 不作为 v2 AgentState。
- **幂等边界**：同 key 绑定指纹与 Turn，pending 不重调，completed 重放复核，failed / discarded 不自动重试；不宣称外部 Provider exactly-once 或 PostgreSQL 实际锁验证。
- **迁移与提交范围**：新增 revision `a196e4c72b08 → f3a96b10d207` 仅源码。后续提交范围须覆盖原 9.6-A 前置实现、M01 与 Extension，不能只采用 21 文件增量实施白名单；无关 C3/BM-01、16 个历史模板删除与 `ad` 不得意外纳入。
- **历史发现与门禁**：原 `9.6A-L01`、`MM-03`、`MM-04` 和 C3/BM-01 保留原有范围及状态，本次零发现不自动关闭它们。Owner-only、默认 ProcessingDecision 关闭、Operator 不等于 Speaker/Consenter，以及真实数据库专项授权 / Manager-Runner 隔离门禁继续有效。

**近期执行顺序**：Documentation Sync（本轮完成）→ Git Commit Readiness Review（待执行，只读核对前置文件、Extension、文档与迁移链）→ 获授权的精确暂存及 Staged Audit → Commit Authorization → Push Authorization。本轮只修改开发日志与路线图，未运行测试、操作 DB/Docker 或执行 Git 写操作；README 与合同归档未改动，其后续同步需求交由提交范围审计核对。

**下一功能阶段**：9.6-B Candidate + immutable Revision + Human Review — NEXT / NOT STARTED，待最小实施范围审批；9.6-C Real Provider — FUTURE / NOT STARTED，依赖真实 Consent 与 Provider 批准。文档同步不启动后续代码开发或授予提交/推送授权。

## Part 9.6-A Provider Extension — Documentation Sync 补充（2026-10-12）

**当前状态：Implementation Completed；Independent Review：PASS；Scope：Offline Provider Extension。**本轮将 README 与合同首页同步为该状态，并保留前述合同草案、工程澄清及两份文档同步的历史记录；未重新运行测试或审查。

### L01 Historical Finding

- Finding：9.6A-L01 — Low OPEN，v1 duplicate end semantics issue。
- Current v2 Provider Extension behavior：
  - repeated end with new key rejected
  - idempotent replay preserved
- Historical finding remains tracked separately；本次文档同步不关闭 L01，也不改变 MM-03、MM-04 或 C3/BM-01 的历史状态。

**验证边界：HTTP/ASGI NOT VERIFIED；PostgreSQL NOT VERIFIED；Real AI Provider NOT IMPLEMENTED。**

**发布分类：DEVELOPMENT SNAPSHOT ONLY。**

**下一阶段：Part 9.6-B Candidate + Revision + Human Review。**

本轮仅修改四份指定文档，保留混合 diff 与原换行格式；未修改业务代码、运行测试、读取 .env / secret、操作数据库 / Docker、执行 migration 或执行任何 Git 写操作。完成后停止，不进入 Git Commit。


## Part 9.6-B — 完整设计草案归档（2026-10-12，最新阶段状态）

- 详细 SSOT：[Candidate + Immutable Revision + Human Review — Contract V1.0](../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。
- 产品决定已确认：Owner 显式选择单条 user/text Message 提取零至多个 Candidate；重跑新批次；人工和 AI 整理采用不可变 Revision＋明确 Owner 审批；新 Memoir 绑定具体批准版本，旧数据保持 Legacy。
- 完善工程草案：四个 workflow 业务表、精确 FK/审批关联、三阶段提取、用途继承、HMAC 指纹、旧 API 切换、迁移与 57 项验收；42 个 Python 拟实施文件（20 新增＋22 修改），不构成本轮写入或 Git 白名单。
- 状态：**REVISED DRAFT — PENDING TARGETED RE-REVIEW**；**IMPLEMENTATION NOT STARTED / NOT AUTHORIZED**；ADR-008 保持 Proposed。离线 Memory 审批 profile 是对 C3/C5 未接线的显式补充，不新建第二审批权威。
- 基线：9.6-A 本地 commit `6c12e96e4f83ada7cb7c7dd60fec4283269f8700`；上方 Git 待提交状态属于历史。本次不推定远端已同步/CI 通过。
- 下一顺序：修订定向再审 → 用户实施批准 → 合成离线实施/验收 → 文档同步 → 另获 Git 授权。HTTP 与专项隔离 PostgreSQL 验证分轨记录；真实数据处理默认关闭，C3/BM-01、C4/C6 状态保持。
- 本次只归档及同步文档；未生成 migration、运行测试/应用、操作 DB/Docker 或写 Git。

## Part 9.6-B — 正式合同审查后最小修订（2026-10-12）

独立合同审查 PASS WITH FINDINGS；已在 [详细合同](../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)补齐 B-CR-01/02/03：旧DELETE引用/回滚兼容、仅分类的TimeoutError证据、已有目标版本与新建例外，并明确同key提交不确定后的只读状态查询。

当前拟实施白名单**42个（20新增＋22修改）**，增补3个Service与3个CRUD的窄删除路径；**57项未来验收**。此前36/48为原审查基线，不能作为修订后的范围授权。

状态：**REVISED DRAFT — PENDING TARGETED RE-REVIEW；IMPLEMENTATION NOT STARTED / NOT AUTHORIZED**。Next：定向再审 → 用户批准完整修订范围 → 合成离线实施与明确授权的验证。HTTP/ASGI、真实PG、DB/Docker和Git仍分别授权；不改变C3/BM-01或生产retention决定。
