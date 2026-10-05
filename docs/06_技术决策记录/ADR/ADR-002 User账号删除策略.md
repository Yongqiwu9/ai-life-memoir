# ADR-002 User账号删除策略

## Status

Proposed

本 ADR 尚未冻结 User Account 删除方式、保留范围或 Owner 转移规则。产品已确认的 Family Archive 删除权限见 ADR-003，讲述者本人数据生命周期见 ADR-006。

Part 9.5.5-C 已冻结 Speaker / Family / 用途分支删除执行合同，见 [Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)，实现尚未开始。下文保留 9.5.5-A 的账号删除议题快照；涉及 Speaker 执行方案的历史 Proposed 描述以 C SSOT 和已更新的 ADR-006 为准。本 ADR 的独立账号注销、Owner 转移和身份处置问题仍未决，状态保持 Proposed。

## Context

User 是登录账号。注销账号可能涉及认证身份、其拥有的 Family、在其他 Family 的协作关系，以及其作为讲述者贡献的内容。三种删除需要分别决定：

| 生命周期 | 删除对象 | 决策状态 |
| --- | --- | --- |
| User Account 删除 | 登录账号及其关联身份、权限 | Proposed；方式和范围未定 |
| Family Archive 删除 | 整个 Family 档案及其下属、派生数据 | Owner 有此权限已 Accepted，见 ADR-003 |
| Speaker Personal Data 删除 | 本人来源数据及可识别派生内容 | 本人有效请求不得被 Owner 否决已确认；执行方案 Proposed，见 ADR-006 |

Owner 可以删除整个 Family，不能据此推定“注销 Owner 账号时自动删除其全部 Family”。Speaker 删除本人数据也不等于删除其登录账号或整个 Family。

## Current Implementation

- User 模型已有 email、password_hash、is_active 等字段；is_active 尚不构成完整账号注销、软删除或匿名化策略。
- User API 只有 GET /api/v1/users/me；认证 API 提供注册和登录。现有 User Service/CRUD 没有账号删除流程。
- Family.owner_id 为非空外键，声明 ondelete="CASCADE"。对应 Alembic 迁移也声明了该数据库级联行为。
- 下游 FamilyMember、Interview、Session、Audio、Transcript、Segment 等外键存在 CASCADE。直接通过 SQL 删除 User 可能沿该关系删除其 Family 数据树。
- User.families 的 ORM relationship 没有显式配置删除级联。ORM 行为与数据库外键级联不能混为一谈，当前声明不能作为账号删除功能已定义的证据。
- 当前没有 FamilyMembership、独立 Participant/Consent 模型，也没有 Memory/MemoryCandidate 实现。关联这些目标概念后的账号删除影响尚未覆盖。

## Proposed Decision

暂不选定 soft delete、hard delete、账号停用、匿名化、所有权转移或历史数据保留方案。进入账号注销实现前，需由产品负责人分别确认账号身份处置、Family 归属和本人来源数据处置，再决定目标流程。

本轮仅记录数据库 CASCADE 风险，不修改外键、ORM relationship、API 或数据库。

## Decision Constraints

- User Account、Family Archive、Speaker Personal Data 是三个不同的生命周期，须分别授权、定义范围并跟踪结果。
- Family Owner 可以删除整个 Family Archive，包括协作者贡献内容；该决定不自动扩展为账号注销规则。
- Owner 不得否决讲述者对本人数据的有效撤回或删除请求。
- 一旦数据被纳入已确认的删除范围，应立即从正常产品访问路径移除；Owner 不提供普通用户恢复入口。
- 备份最终清除周期未定，不写死期限；本 ADR 不确定法律留存义务或不可逆物理清除时间。

## Consequences

### Positive

- 避免将现有数据库外键行为误当作产品政策。
- 保留分别处理账号身份、Family 档案和讲述者贡献的能力。

### Negative / Trade-offs

- 账号注销功能仍需要产品决策和实施设计，不能直接复用 Family 删除 API。
- 所有权转移、协作者贡献和讲述者追踪会增加未来删除流程的协调成本。

## Security & Privacy Impact

账号停用、撤销访问、删除内容和物理清除是不同效果。需要确认注销后哪些身份和内容仍可见，以及审计信息是否保留、保留什么。不得将 CASCADE 或 is_active 作为已满足隐私处置要求的依据。

## Migration Impact

本轮无数据库变更。后续可能需要评估 User→Family 外键、ORM 关系、身份关联和删除流程；具体迁移须待政策明确后通过 Alembic 实施。不得提前推定历史数据删除、身份回填或 Owner 转移规则。

## Open Questions

1. 是否允许用户自主注销账号，申请身份如何验证？
2. 账号采用停用、soft delete、hard delete 或匿名化中的哪种方式，是否存在不同阶段？
3. Owner 注销时，其 Family Archive 删除、保留还是转移？谁可以接任 Owner，如何同意？
4. 注销账号在其他 Family 的协作关系与历史贡献如何处理？注销是否同时构成本人来源数据删除请求？
5. 已确认 Memory、多人来源内容和历史讲述者身份是否保留，如何去除或匿名化账号关联？
6. 哪些审计信息需要保留，其范围、访问权限和期限是什么？
7. 主存储不可逆清除、备份最终清除周期及可能的法律留存如何确定？

## Related Documents

- [ADR-003 Family档案删除策略](<ADR-003 Family档案删除策略.md>)
- [ADR-005 Interview参与者与讲述者模型](<ADR-005 Interview参与者与讲述者模型.md>)
- [ADR-006 Consent授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)
- [技术债登记表 TD-9.3-01 / TD-9.5-03](../技术债登记表_V1.0.md)
- [Database Schema Evolution](<../../02_数据模型/Database Schema Evolution_V1.0.md>)

## Related Code

- [User Model](../../../apps/backend/app/models/user.py)
- [Family Model](../../../apps/backend/app/models/family.py)
- [User API](../../../apps/backend/app/api/v1/users.py)
- [Auth API](../../../apps/backend/app/api/v1/auth.py)
- [User Service](../../../apps/backend/app/services/user.py)
- [User CRUD](../../../apps/backend/app/crud/user.py)
- [Family / FamilyMember 现有迁移（只读依据）](../../../apps/backend/alembic/versions/d7fd7c838c56_create_families_and_family_members.py)

## Revision History

| 日期 | 变更 |
| --- | --- |
| 2026-10-05 | Part 9.5.5-A：原 ADR-002 User删除策略 更名并扩充为账号删除议题；保留 Proposed，区分三个生命周期，记录当前 CASCADE 风险。 |
