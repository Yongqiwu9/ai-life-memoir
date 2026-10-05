# ADR-004 Family协作权限模型

## Status

Proposed

家庭协作的产品方向已确认；最终权限矩阵、编辑审批方式和实际数据结构尚未冻结。已确认原则记录在 Decision Constraints，不因本 ADR 为 Proposed 而失效。

## Context

首版需要支持多个登录账号共同访问同一 Family 档案。当前单一 Owner 查询无法表达邀请、加入、协作者访问或 Owner 对编辑的同意。

必须区分档案里的家庭人物与有权访问档案的账号。FamilyMember 表示回忆档案中的人物，不能通过创建一个 FamilyMember 就给同名账号授予访问权，也不能把 FamilyMember 列表直接当成协作者列表。

## Current Implementation

- `Family` 只有 `owner_id` 这一账号归属；当前没有 FamilyMembership 或协作角色模型。
- Family Service / CRUD 使用 `Family.id + owner_id` 校验和查询。FamilyMember、Interview 及其 Session / Message / Audio / Transcript 数据继续沿归属链检查同一个 Owner。
- API 从 JWT 得到当前 User。现有 Family/FamilyMember/Interview 的创建和编辑操作没有邀请或 Owner 审批流程。
- `FamilyMember` 只有 `family_id`、`name` 与基础主键/时间字段，没有与 User 的登录身份映射。
- 当前 Owner-only 是已经实现的访问限制，不能表述为目标产品只允许 Owner 使用；本轮也没有放宽代码中的该限制。

## Proposed Decision

### Target Design

拟以 FamilyMembership 这一访问关系概念表达账号加入家庭档案：

```text
User
  ↓
FamilyMembership（目标概念，尚未实现）
  ↓
Family
```

至少区分 Owner 与 Collaborator。Backend 依据已获准的 Family 访问关系、操作权限和相关 Consent 校验请求。FamilyMember 继续表示档案人物，不承担账号角色或访问授权职责。

协作者可以提出邀请申请；实际加入需要 Owner 同意。协作者编辑需要 Owner 同意，但逐次审批与持续编辑权限尚未选定。具体 RBAC 表结构、Membership 状态、邀请令牌及接口均不在本轮冻结。

### Product Decision

首版支持 Family Collaboration 是已确认方向；单独个人档案系统不是必需模块。默认“回忆我自己”仍沿用 Family / FamilyMember / Interview 统一领域模型。

协作者的目标访问范围以 Family 档案为单位。此前确认的家庭范围可见原则仍须受到有效 Consent、撤回和删除限制；原始 Audio 的可见权限尚未明确，不能从“全 Family 可见”自行推导。

## Decision Constraints

1. Owner 与 Collaborator 至少需要区分；不能将当前 `Family.owner_id` 校验简单改为“任何登录 User 都可访问”。
2. 已加入的协作者可以提出邀请申请；邀请对象加入 Family 必须经过 Owner 同意。
3. 协作者提出的编辑必须得到 Owner 同意；不得在未确认前选定逐次审批或持续编辑权限。
4. Owner 可以删除整个 Family Archive；该权限与 Speaker 本人有效撤回/删除请求分离，Owner 不得否决后者。
5. Membership 不能替代 Speaker 的 Consent；具有自主决定能力的成年讲述者必须本人同意录音、转写、AI 分析和家庭共享。
6. 账号、档案人物、协作者访问关系和实际讲述者必须区分；拥有其中一种身份不自动意味着拥有其他身份。
7. 保持跨 Family 隔离。当前用户身份继续来自 JWT，不能信任客户端传入的 User、角色或 Owner 标识。

## Consequences

### Positive

- 同一 Family 可以容纳多个获准账号，不必复制档案或把协作者伪装成 FamilyMember。
- Owner 同意与讲述者本人 Consent 各自有明确职责，便于后续邀请、提取和确认流程衔接。
- 当前单人使用可以沿统一模型演进到家庭协作。

### Negative / Trade-offs

- 需要审查当前所有 Owner-only 查询和资源归属路径；只放宽最上层 Family API 会产生权限不一致。
- 编辑审批方式尚未确定，无法据此冻结写入接口、数据版本和审批记录结构。
- Family 范围访问需要同时考虑撤回后历史来源隐藏，不能仅检查 Membership。

## Security & Privacy Impact

目标权限检查应由 Backend 的 Service / 查询层落实，同时验证资源所属 Family、访问关系和实际操作许可。Client 不直接访问数据库或 AI Provider。

协作者的邀请能力不是绕过 Owner 的加入权限。协作者身份也不自动授予原始音频访问、候选记忆确认或整体档案删除权限。权限撤销后的具体处理、历史副本处理以及实时会话中的授权更新仍需决定。

## Migration Impact

本轮不创建 FamilyMembership Model，不修改现有 owner_id、Schema、Service 或 API，不创建和执行迁移。

未来若采纳此模型，需经单独实施计划决定如何表达 Membership、保留 Owner 归属并迁移现有 Owner-only 数据。不得在迁移时根据 FamilyMember 的姓名推断 User 身份、协作者资格或本人同意。

## Open Questions

- Collaborator 是否可以创建 Interview？该创建行为是否需要 Owner 审批？
- Collaborator 是否可以查看或播放原始 Audio？
- Collaborator 是否可以确认 MemoryCandidate？Owner 是否唯一确认者？
- 编辑采用每次逐项审批，还是 Owner 授予持续编辑权限？持续权限若被撤销，如何处理进行中的编辑？
- 邀请的接收身份、有效期、撤销、拒绝和重复邀请如何处理？
- Owner 撤销 Collaborator 访问后，对方贡献的来源、本人 Consent 和删除请求如何继续处理？
- Owner 是否可转移所有权？User Account 删除与 Family Ownership 如何协调？
- 最终权限矩阵、Membership 状态、审批与版本记录的数据结构是什么？

## Related Documents

- [系统架构总览](../../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Memory 生成链路设计](../../04_AI设计/Memory生成链路设计_V1.0.md)
- [ADR-002 User账号删除策略](<ADR-002 User账号删除策略.md>)
- [ADR-003 Family档案删除策略](<ADR-003 Family档案删除策略.md>)
- [ADR-005 Interview参与者与讲述者模型](<ADR-005 Interview参与者与讲述者模型.md>)
- [ADR-006 Consent授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)
- [ADR-008 MemoryCandidate确认流程](<ADR-008 MemoryCandidate确认流程.md>)

## Related Code

- [User Model](../../../apps/backend/app/models/user.py)、[Family Model](../../../apps/backend/app/models/family.py)、[FamilyMember Model](../../../apps/backend/app/models/family_member.py)
- [Family Schema](../../../apps/backend/app/schemas/family.py)、[FamilyMember Schema](../../../apps/backend/app/schemas/family_member.py)
- [Family Service](../../../apps/backend/app/services/family.py)、[FamilyMember Service](../../../apps/backend/app/services/family_member.py)、[Interview Service](../../../apps/backend/app/services/interview.py)
- [Family CRUD](../../../apps/backend/app/crud/family.py)、[Family API](../../../apps/backend/app/api/v1/families.py)、[FamilyMember API](../../../apps/backend/app/api/v1/family_members.py)

## Revision History

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-10-05 | V1.0 | Part 9.5.5-A；记录家庭协作已确认约束与 Proposed 访问关系模型，保留权限矩阵和编辑审批方式的未决项。 |
