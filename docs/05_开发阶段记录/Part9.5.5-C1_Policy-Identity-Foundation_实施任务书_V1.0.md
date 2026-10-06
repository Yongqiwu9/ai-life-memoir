# Part 9.5.5-C1 — Policy + Identity Foundation 实施任务书 V1.0

## 文档状态

- Document Type：Implementation Task
- Part：9.5.5-C1
- Status：Archived Task Specification
- Design Baseline：Part 9.5.5-C Design Frozen
- Git Baseline：`ade0f0ca2dbecab474d315a853b2e7721e9e9609`
- Feature Completion：本文件不声明功能完成；实施与验证状态以 README、路线图和开发日志为准

> `Implementation Task` 是实施任务边界，不是 Completed Feature Report。Design Frozen 也不等于 Feature Implemented。

## 1. Source of Truth

实施必须依次遵循：

1. 根目录 `AGENTS.md` 与 `apps/backend/AGENTS.md`。
2. README、Part 开发路线图、技术债登记表。
3. [Part 9.5.5-C Final Implementation Design Freeze](../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)。
4. ADR-004、ADR-005、ADR-006 及现有数据模型文档。
5. 当前 Backend Auth/User、Alembic 与 PostgreSQL integration test infrastructure。

冻结设计是产品与数据语义 SSOT。本任务不得修改其冻结语义。

## 2. Git 与工作区安全

- 起始 HEAD：`ade0f0ca2dbecab474d315a853b2e7721e9e9609`。
- 保留 16 项既有 docs 模板删除为 unstaged。
- 保留 `ad` 为 untracked，不读取、不修改。
- `apps/backend/.env.test` 必须保持 ignored，不输出其中秘密。
- 本任务禁止 `git add`、commit、push、clean、hard reset、restore whole tree。

## 3. C1 实施范围

C1 只实现：

1. `PrivacyPolicyVersion`。
2. 现有 `User` 的 `principal_kind` 与 `auth_generation`。
3. `UserContact`。
4. `AuthChallenge`。
5. rights-only authentication foundation。
6. 必要 Schema、CRUD、Service、Dependency 与 Security 调整。
7. 最小 rights-auth API。
8. 一个 Alembic revision。
9. Fast 与 PostgreSQL integration tests。
10. 必要项目文档同步。

禁止提前实现：FamilyMembership、FamilyInvitation、InterviewParticipant、ConsentGrant、ConsentEvent、SourceArtifact、DeletionRequest、SanitizationRun、MemoryCandidate，以及 C2+ 的占位表或 API。

## 4. Privacy Policy Version

- Policy 状态为 draft、active、retired；最多一个 active。
- draft 可以不完整，但已提供字段必须满足类型和取值约束。
- active 必须包含冻结设计要求的全部 Policy 参数、告知内容及经验证能力证据。
- 所有 duration 使用显式正整数 `seconds`，不得设置未经确认的生产默认期限。
- `sanitization_retry_limit` 是独立的非负整数。
- sanitization review 不得延长 online deletion deadline。
- deletion ledger retention 必须覆盖 backup、object version、database recovery 和 late-job 窗口。
- 已发布 Policy 的版本、参数、告知、能力、digest 和 published_at 不可修改，不得重新激活或删除。
- active Policy 缺失、不完整、被篡改或能力未验证时，新采集、Consent、历史恢复、净化发布及外部处理必须 fail closed。
- Withdrawal / Deletion 安全路径不得因 active Policy 缺失而被拒绝，但 C1 不实现这些业务流程。

## 5. Unified User Principal

- 继续使用现有 `User` 作为唯一认证主体，不创建平行身份体系。
- `principal_kind` 只允许 account、rights_only、system。
- account 必须具有满足当前登录要求的 email/password_hash。
- rights_only 与 system 不得持有普通密码凭据，也不得通过 password login 获得 account session。
- `auth_generation` 必须非空且大于零；token 与数据库 generation 不一致时立即拒绝。
- 历史 User 只安全回填为 account / generation=1，不自动创建 rights_only。

## 6. UserContact

- Contact 属于现有 User，不是新身份。
- 支持 email / phone 与 pending、verified、revoked、legacy_unverified 状态。
- 保存加密接口输出与使用服务器密钥的不可逆 lookup hash；不得保存明文联系方式。
- pending / verified 的有效渠道必须满足唯一性；revoked / legacy 状态不能成为隐式账号恢复或合并路径。
- 历史 `User.email` 不得自动生成 verified UserContact，也不能作为 Speaker 身份或 Consent 证据。
- User FK 使用 RESTRICT。

## 7. AuthChallenge 与 Rights Authentication

- Challenge 必须具有不可变 context、渠道密文、lookup hash、code digest 和 expiry。
- OTP 使用安全随机值，数据库只保存上下文绑定 digest，不保存明文。
- 实现 pending、verified、consumed、expired、locked 生命周期、尝试上限、过期拒绝、事务消费及重放拒绝。
- 创建 challenge 返回通用 receipt，避免枚举身份；冲突、失败和错误响应不得泄露联系方式、OTP、ciphertext、lookup hash 或 digest。
- rights token 与 account token 必须通过 token type、scope、principal kind 和 generation 隔离。
- rights token 只提供 `rights:identity`，不得获得 Family、Interview 或 account-only API 访问权。
- account token 不自动获得 Speaker rights。
- rights 身份入口独立于 account `is_active`，但仍受 generation、verified Contact 和已消费 Challenge 约束。
- 旧的无 token type / auth_generation JWT 需要重新登录，这是预期兼容策略。

## 8. Production Capability Boundary

- Production encryption provider：NOT IMPLEMENTED。
- Production contact verification delivery：NOT IMPLEMENTED。
- Production key management：NOT IMPLEMENTED。
- Production rate limiting adapter：NOT IMPLEMENTED。
- 未安装并验证这些能力时，rights-auth 必须 fail closed / 503。
- 测试内存 vault 只能标记为 TEST ONLY，禁止描述为 production-ready encryption。

## 9. Migration Contract

- 仅创建 `privacy_policy_versions`、`user_contacts`、`auth_challenges`，并修改现有 `users`。
- 使用 PostgreSQL 原生 JSONB、BYTEA、TIMESTAMPTZ、CHECK、FK 与 partial unique index。
- migration 必须对既有 User 安全 backfill，不伪造 verified Contact、密文或验证证据。
- 不修改历史 migrations，保持单 head。
- downgrade 必须在存在 C1 隐私/安全数据、非 account 主体或 generation 变化时拒绝，不能静默丢失证据。
- 迁移验证只能使用经过安全校验、数据库名含 `test` 的 `TEST_DATABASE_URL` 和显式 `TEST_MIGRATION_MODE=1`；不得回退到开发库。

## 10. Required Validation

必须验证：

- Ruff check 与 format check。
- 最新完整 fast suite。
- PostgreSQL fresh upgrade、single head、current、Alembic check。
- PostgreSQL integration suite 及测试后的 current/check。
- register、login、users/me、Family、Interview 的账号回归。
- rights/account 隔离、system/rights_only 密码登录拒绝、generation 失效、Contact 撤销、Challenge 过期/锁定/重放、OTP 非明文、反枚举及 PII 不泄露。
- draft incomplete allowed、incomplete active rejected、published Policy mutation rejected、missing production capability returns 503。
- migration backfill、数据库约束、类型、唯一性、FK RESTRICT 与 downgrade guard。

只有 Fast、PostgreSQL、Alembic final check、安全边界测试全部通过，且不存在 Critical/High implementation flaw，才能将 C1 标记为 Implemented / Validated 并进入 C1 pre-commit audit。

## 11. Documentation Status Rule

- Part 9.5.5-B：Completed。
- Part 9.5.5-C Design：Design Frozen。
- Part 9.5.5-C Implementation：In Progress。
- C1：只有最终验证闭环后才能写 Implemented / Validated。
- C2：Not Started / Next。
- Part 9.6：Planned。
- 不得把整个 Part C 标记为 Completed。

## 12. Deliverable Boundary

本任务交付 C1 foundation 与验证证据，不授权暂存、提交、推送或进入 C2。最终报告必须明确测试计数、迁移状态、安全边界、生产能力缺口、scope guard 和 Git 安全状态。
