# ADR-003 Family档案删除策略

## Status

Accepted

本 ADR 冻结产品负责人已经确认的 Family Owner 删除权限及相关边界。Accepted 不表示删除流程、对象存储清理或备份清除已经实现，也不表示尚未确定的保留期限已经冻结。

## Context

家庭协作将使同一 Family 档案包含 Owner 与协作者贡献的资料。Memory Extraction 还会在来源资料上产生候选记忆和确认后的记忆，因此必须明确 Owner 能否删除整个档案，以及该权限与讲述者本人请求之间的关系。

以下三种生命周期必须分别判断，不能因现有外键级联而互相代替：

| 生命周期 | 请求对象 | 本 ADR 的范围 |
| --- | --- | --- |
| User Account 删除 | 登录账号以及其账号关系 | 不在本 ADR 冻结范围，见 ADR-002 |
| Family Archive 删除 | 整个家庭档案及其归属数据 | 本 ADR 冻结 Owner 的删除权限 |
| Speaker Personal Data 撤回/删除 | 本人讲述的来源与可识别派生内容 | 独立权利和流程，见 ADR-006；Owner 不得否决有效请求 |

Family Archive 是产品范围的概念，当前没有独立的 `FamilyArchive` 数据表或模型。

## Current Implementation

- `Family.owner_id` 指向 `User`，外键声明 `ondelete="CASCADE"`。当前 Owner 查询以 `Family.id` 和 `owner_id` 同时过滤。
- `DELETE /api/v1/families/{family_id}` 从 JWT 取得当前 User；Service 先查找其拥有的 Family，CRUD 调用 `db.delete(family)` 并提交。
- Family 下已有 FamilyMember、Interview、InterviewSession、InterviewMessage 和 Audio/Transcript/Segment 的模型与元数据 API；主要归属外键声明 CASCADE。
- ORM 关系的删除配置不完全一致，例如 `FamilyMember.interviews`、`InterviewSession.audio_recordings` 未配置 ORM 删除级联或 `passive_deletes`。因此不能仅依据外键声明就断言现有 API 已完成或已经验证全链删除。
- `InterviewMessage.transcript_segment_id` 为 `SET NULL`；单独删除 Segment 不会凭该外键删除 Message。来源删除不能仅通过断开引用实现。
- 当前没有 FamilyMembership、讲述者身份、Consent、本人数据删除申请或派生内容清理实现。MemoryCandidate / Memory 尚未实现。
- AudioRecording 当前只是元数据；没有实际音频上传、对象存储和 STT Provider 集成。没有可据此宣称已完成的音频二进制或第三方清理流程。

## Decision

### Product Decision

Family Owner 可以删除整个 Family Archive，包括 Owner 自己创建的数据和协作者贡献的数据。范围涵盖 Family 下的 FamilyMember、Interview、Session、Message、Audio、Transcript、TranscriptSegment，以及未来归属于该 Family 的 MemoryCandidate、Memory 和其他派生档案数据。

Owner 删除整个 Family Archive 与 Speaker 对本人来源及可识别派生内容提出有效撤回/删除请求是两个独立流程。Owner 的整体删除权限不能解释为 Owner 可以否决 Speaker 的有效请求，也不能解释为 Owner 可以代替具有自主决定能力的成年讲述者给予 Consent。

### Target Design

未来删除流程需要以 Family 为范围识别其归属数据，并覆盖实际部署后使用的媒体存储、派生数据与正在执行的处理任务。删除请求完成产品访问限制后，相关内容不得继续通过正常产品路径访问或继续处理。

Part 9.5.5-C 已冻结逻辑隔离、在线清除、衍生物清除、第三方清除、备份淘汰及声明范围清除完成的独立 Deletion Pipeline 合同，以及来源追踪、最小化 Deletion Ledger 和净化上限规则。详细结构与状态机仅保存在 [Part 9.5.5-C Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md) 第 3、6、7、9、10 部分；本 ADR 不重复表结构。

DESIGN FROZEN != FEATURE IMPLEMENTED：上述流程尚未实现。生产 retention 值及 Storage / Backup / Provider 能力仍待确认；Family 删除不自动决定 User Account 删除或 Ownership Transfer，ADR-002 继续 Proposed。

## Decision Constraints

1. 删除的数据应立即从正常产品访问路径移除并停止相关处理；Owner 不提供普通用户恢复入口。
2. Speaker 对本人数据的有效撤回/删除请求不得等待 Owner 许可，也不得被 Owner 否决。
3. 多人来源的派生内容需要识别来源并处理受影响部分；具体拆分/重新生成算法未实现，不能把全部混合内容直接归为 Owner 数据。
4. 备份最终清除周期、不可逆物理清除时间、法定留存要求尚未确定；不得在此写死任何天数或期限。
5. Accepted 冻结已确认的产品边界及 C 的设计合同，不表示 Migration 已执行或清除已验收；当前 CASCADE 声明不能代替该生命周期合同。

## Consequences

### Positive

- Owner 的档案管理权限明确，未来加入协作者时可以保持统一的 Family 删除范围。
- Family 删除与 Speaker 本人请求分开，避免将家庭管理权限误用为对本人来源数据的否决权。
- 后续 Memory 设计有明确的归属和清理边界。

### Negative / Trade-offs

- 整体删除会影响协作者贡献的数据，需要明确告知影响范围；告知渠道与流程仍未确定。
- 仅删除数据库主记录不能完成媒体、派生内容、第三方数据和备份的清理，需要未来分别落实。
- 多人来源派生内容增加来源追踪和清理协调的成本。

## Security & Privacy Impact

未来 Backend 处理 Owner 的整体删除请求时必须校验请求者确为该 Family 的 Owner，不能信任客户端提交的 `owner_id`。Collaborator 无整体 Family 删除权；作为经过核验的 Speaker，可独立请求删除本人来源及受影响衍生物，无须 Owner 批准。完整矩阵见 C SSOT 与 ADR-004/006。

撤回后隐藏历史内容与永久删除是不同处理阶段。产品访问移除需要覆盖普通读取及派生内容读取；备份、第三方副本和物理清除的限制必须如实说明，不能把访问隐藏描述为已经完成物理清除。

## Migration Impact

本次同步仅归档设计和更新 ADR，不修改代码、数据库结构或数据，不创建或执行 Alembic migration。

后续实施按 C SSOT 的迁移顺序核对数据归属、外键及 ORM 删除行为，并落实 Registry、隔离及独立清理服务。Membership、Consent、Participant 及未来 Memory 均需纳入生命周期，不能直接复制现有 CASCADE 作为产品结论。

## Open Questions

- 生产 Policy 的具体清除与保留期限，需在 Storage / Backup / Provider 能力验证后单独冻结；不得自行填入默认天数。
- 整体删除前的范围展示与受影响协作者通知界面仍需落实，不能阻止有效请求进入隔离与删除流程。
- 实际媒体、Provider、缓存和备份的 cleanup adapter / evidence protocol 及能力验证尚未完成；冻结合同不能替代执行证据。
- User Account 删除、Owner 转移及任何法定留存例外仍不在 C 的冻结范围；按 ADR-002 独立处理，不得由实现自行推定。

## Related Documents

- [系统架构总览](../../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型设计基线](../../02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [技术债登记表](../技术债登记表_V1.0.md)，TD-9.3-01、TD-9.5-03。
- [ADR-002 User账号删除策略](<ADR-002 User账号删除策略.md>)
- [ADR-004 Family协作权限模型](<ADR-004 Family协作权限模型.md>)
- [ADR-006 Consent授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)

## Related Code

- [Family Model](../../../apps/backend/app/models/family.py)、[FamilyMember Model](../../../apps/backend/app/models/family_member.py)
- [Interview Model](../../../apps/backend/app/models/interview.py)、[Session Model](../../../apps/backend/app/models/interview_session.py)
- [Message Model](../../../apps/backend/app/models/interview_message.py)、[Audio Model](../../../apps/backend/app/models/audio_recording.py)、[Transcript Model](../../../apps/backend/app/models/transcript.py)、[Segment Model](../../../apps/backend/app/models/transcript_segment.py)
- [Family API](../../../apps/backend/app/api/v1/families.py)、[Family Service](../../../apps/backend/app/services/family.py)、[Family CRUD](../../../apps/backend/app/crud/family.py)

## Revision History

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-10-05 | V1.0 | Part 9.5.5-A；将已确认的 Owner 整体删除权限记录为 Accepted，保留具体删除和留存机制的未决项。 |
| 2026-10-05 | V1.1 | 引用 Part 9.5.5-C 冻结删除合同；移除已解决的机制未决项，保留生产能力/期限与独立账号政策；未实施删除功能。 |
