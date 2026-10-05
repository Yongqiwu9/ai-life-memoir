# ADR-004 Family协作权限模型

## Status

Accepted

Implementation: Not Started

本 ADR 摘要记录 Part 9.5.5-C 已冻结的 Family 协作、邀请、修订审批和权限边界。完整表结构、状态机、API 合同、迁移顺序与验收矩阵以 [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md) 为唯一事实来源。Accepted 表示设计已冻结，不表示功能已经实现。

## Context

首版需要支持多个账号共同访问同一 Family 档案。档案人物、账号访问关系、访谈参与关系和实际来源讲述者承担不同职责，不能通过同名 FamilyMember、客户端角色或当前调用者相互推定。

## Current Implementation

- `Family` 只有 `owner_id` 这一账号归属；当前没有 FamilyMembership、FamilyInvitation 或修订审批模型。
- Family Service / CRUD 使用 `Family.id + owner_id` 校验和查询。FamilyMember、Interview 及其 Session / Message / Audio / Transcript 数据继续沿归属链检查同一个 Owner。
- API 从 JWT 得到当前 User。现有 Family/FamilyMember/Interview 的创建和编辑操作没有邀请或 Owner 审批流程。
- `FamilyMember` 只有 `family_id`、`name` 与基础主键/时间字段，没有与 User 的登录身份映射。
- 当前 Owner-only 是已经实现的访问限制；Family Collaboration 及本 ADR 的目标权限尚未实现。

## Decision

### Owner 与 Membership

- `Family.owner_id` 继续作为 Owner 的唯一权威来源。
- FamilyMembership 只保存 Collaborator，不重复建立第二个 Owner 来源；至少记录 active、revoked、left 状态和 generation。
- active Collaborator 可以在 Family 范围内读取允许的元数据、创建 Interview，并追加自己的原始文字来源或协助发起录音。内容读取、录音、处理和分享仍须通过来源、Participant、Consent 和删除门禁。
- Membership 撤销立即取消普通 Family 访问；不删除历史贡献，也不取消 Speaker 的本人权利入口。
- 跨 Family 隔离继续由 Backend Service / 查询层执行。身份、角色和 Owner 标识来自服务端认证及持久化关系，不信任客户端传入值。

### Invitation

- Owner 或 active Collaborator 可以发起邀请。Collaborator 发起后进入 Owner 审批；Owner 发起可直接批准。
- 被邀请账号只有在 Owner 已批准且本人核验并接受后，才建立 active Membership。
- 邀请的拒绝、取消、撤销和过期均不得产生 Membership；重新加入必须经过新邀请。

### 编辑、审批与删除权限

- Collaborator 对已有内容的修改必须形成不可变 RevisionProposal；Owner 按精确目标版本、内容摘要和当前权限门禁审批后才成为当前版本，不能覆盖原始来源。
- Speaker 与 Collaborator 可以提交本人纠错或修订；MemoryCandidate 在后续 9.6 实现中由 Owner 最终批准。批准不能替代当前 Consent、来源归属或删除门禁。
- Owner 可以删除整个 Family Archive。Collaborator 不自动获得整体档案删除权；未明确开放的 FamilyMember / Interview 子树删除入口不得继续直接硬删。
- Owner、Collaborator 和 Worker 都受 Speaker Consent、隔离与删除状态约束。Family 分享不自动允许普通 Collaborator 播放原始 Audio；原音还需要明确的 raw_audio 分享许可。

## Consequences

### Positive

- Owner 归属与 Collaborator 访问只有一个清晰来源，不会因重复 Owner Membership 产生冲突。
- 邀请、加入、撤销和重新加入均可审计，协作者不能绕过 Owner 批准扩张访问范围。
- 原始来源与协作者修订分离，Owner 审批精确版本，同时保留来源追溯与 Speaker 权利。

### Trade-offs

- 所有现有 Owner-only 查询都需要按完整资源链切换，不能只放宽 Family 顶层入口。
- 访问判断必须同时考虑 Membership generation、来源归属、Consent epoch、修订版本和删除状态。
- 直接硬删接口需要改为显式删除流程或关闭，不能依赖数据库级联表示业务完成。

## Security & Privacy Impact

FamilyMembership 只表达账号访问关系，不能替代 Participant、Speaker 归属或本人 Consent。revoked Membership 的旧 JWT 不再具有 Family 访问权；rights_only Speaker 会话也不能获得普通 Family 浏览、创建或邀请权限。

Owner 审批只确认协作操作或修订版本，不允许代替自主成年 Speaker 授权，也不能恢复已撤回、隔离、待删除或已删除的来源。

## Migration Impact

本 ADR 更新仅归档设计，不创建 Model、Schema、Service、API 或 Alembic revision。后续实现按 SSOT 追加迁移：保留 `Family.owner_id`，将其外键删除行为调整为 RESTRICT，新增 Invitation / Membership / Revision 等结构，并在完整权限门禁切换前保持当前 Owner-only 行为。

历史数据不得通过 FamilyMember 姓名推断 User、Collaborator、Participant、Speaker 或 Consent。V1 不开放 User hard delete、Owner 转移或身份自动合并。

## Future Boundaries

- User Account 删除、Owner 转移及账号匿名化继续由 ADR-002 单独决定。
- 实际 Audio 上传、对象存储、STT/LLM 和媒体清理适配器不因本 ADR Accepted 而视为完成。
- Policy 的生产期限与告知文本通过后续能力核验和配置启用；缺值时执行 SSOT 已冻结的 fail-safe。

## Related Documents

- [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)
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
| 2026-10-05 | V1.0 | Part 9.5.5-A；记录家庭协作约束与 Proposed 访问关系。 |
| 2026-10-05 | V1.1 | Part 9.5.5-C Design Freeze；冻结 Owner/Membership、邀请、不可变修订、Owner 审批及权限门禁；Implementation Not Started。 |
