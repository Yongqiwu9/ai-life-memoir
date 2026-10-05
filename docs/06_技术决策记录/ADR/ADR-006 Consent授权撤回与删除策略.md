# ADR-006 Consent 授权、撤回与删除策略

## Status

Proposed

产品负责人已确认的原则列在 Decision Constraints。Consent 的身份验证、记录结构、处理流程和删除传播方案尚未冻结，本 ADR 不代表相关功能已实现。

## Context

真实讲述者可能与登录 User、Family Owner、Interview subject 不同。一个 Interview 只有一个主要回忆对象，但可以有多个实际讲述者。家庭访问权限不能代替讲述者对自身内容处理的授权。

Consent 至少需要区分录音、转写、AI 分析和 Family 范围共享四类用途。撤回授权、请求删除本人来源数据和 Owner 删除整个 Family Archive 是不同操作；User Account 删除另见 ADR-002，Family Archive 删除另见 ADR-003。

## Current Implementation

- 当前资源访问通过 `Family.owner_id` 沿 Interview / Session / Audio / Transcript 等关系校验 Owner；尚无 FamilyMembership、InterviewParticipant / Speaker 身份关系或 Consent 模型/API。
- `Interview.family_member_id` 指向回忆对象。`InterviewMessage.role=user` 只表示对话角色，不能证明哪位真人提供了内容；`TranscriptSegment.speaker` 为可空字符串，不能作为本人身份验证或授权证据。
- AudioRecording、Transcript、TranscriptSegment 只有元数据模型/API。没有实际录音上传、对象存储、外部 STT 调用、授权撤回处理或本人来源数据删除流程。
- Message 可以通过 `transcript_segment_id` 回链 Segment。该外键是 `ON DELETE SET NULL`：删除 Segment 会断开回链，但不会自动删除 Message 内容。因此不能把删除 Segment 等同于删除其全部来源内容或派生数据。
- Family 删除及关联数据的级联关系已经存在，但尚不具备按实际讲述者定位来源、隐藏历史内容或传播删除的能力。MemoryCandidate、Memory、AI Service 仍未实现，不能宣称多人派生数据删除已完成。

## Proposed Decision

### Target Design

在未来授权流程中，分别记录和检查录音授权、转写授权、AI 处理授权及家庭共享授权。授权作用范围是 Family、Interview、Session 还是具体来源数据，以及是否允许独立授予/撤回各类用途，需要产品确认后再定。

Consent 不应仅用一个简单 boolean 表示。审计需要能回答：谁对什么内容、在什么时候授予了哪些用途、什么时候撤回，以及对应的授权说明与身份确认依据。这里只记录能力要求，不确定数据库表、字段、枚举或 API。

未来 Backend 在业务访问和处理入口执行授权检查；实际讲述者身份、来源追踪与撤回记录应可关联。对异步队列、处理中任务、结果回写、导出和派生内容的控制点需要设计，避免撤回后继续处理或使隐藏内容重新出现。具体取消、隔离、删除和重生成机制仍为 Proposed。

本人来源删除请求需要追踪 Audio、Transcript、Segment、Message/source data 及可识别派生内容。对混合多人来源的 Memory，目标是尊重有效删除请求，同时识别受影响的来源和派生内容；具体拆分、重生成、审批及版本处理规则尚未确定，也尚未实现。

## Decision Constraints

以下为已确认 Product Decision，不因本 ADR 的 Proposed 状态而被重新推定：

1. 实际讲述者须同意录音、转写、AI 分析和 Family 范围共享；Owner 不能代替具有自主决定能力的成年讲述者给予同意。
2. 讲述者撤回 Consent 后，未来针对其内容的录音、转写、AI 分析和 Family 共享必须停止；相关历史内容首先从其他协作者视角隐藏。
3. 讲述者可以要求删除自己的 Audio、Transcript、Message/source data 和可识别派生内容。Owner 不能否决讲述者对本人数据的有效删除请求。
4. Owner 可以删除整个 Family Archive，包括协作者贡献内容。该权力不替代或否决讲述者对本人来源数据的撤回/删除权。
5. 删除数据应立即从正常产品访问路径中移除，Owner 不提供普通用户恢复入口。立即移除不代表所有数据库、对象存储、第三方副本或备份已同步完成物理清除。
6. 备份最终清除周期尚未确定，不设定任何固定天数；多人来源 Memory 的拆分/重生成算法未实现。

## Consequences

### Positive

- 将家庭访问权限与本人授权分开，避免 Owner 身份被误用为替他人同意的依据。
- 为 Memory 提取、来源追踪及本人删除请求建立同一授权边界。
- 保留授权和撤回的审计能力，便于检查处理是否发生在有效授权范围内。

### Negative / Trade-offs

- 需要补充讲述者身份和来源归属，当前 Owner-only 访问链不足以支撑。
- 撤回后的隐藏、异步任务停止、派生内容处理和备份清除涉及多个生命周期。
- 多讲述者贡献可能混在同一音频或 Memory 中，不能仅凭外键级联删除完成本人数据请求。

## Security & Privacy Impact

家庭成员访问权、Owner 审批和 Consent 是不同检查。AI 提取必须检查相应用途的授权，不能从拥有 Family 或能够读取 Message 推定 AI 处理同意。

撤回后的历史隐藏必须在服务端访问和处理路径生效。审计记录本身也包含身份与操作信息，其可见范围、内容最小化和保留期需要明确；不能把保留审计解释为继续保留已请求删除的完整讲述原文。

## Migration Impact

本轮没有创建 Consent / Participant 模型，没有修改数据库或 Alembic。未来实施可能需要支持身份关联、授权审计、来源追踪、访问屏蔽和删除进度；具体结构须在 Open Questions 解决后另行设计，并通过 Alembic 迁移。

现有历史内容没有可验证的讲述者身份和同意记录，不能自动回填为“已授权”。历史内容进入 AI 处理、共享或继续保留的条件需要产品决定。

## Open Questions

- 没有登录账号的讲述者如何验证身份并由本人表达同意？不具备自主决定能力或未成年讲述者如何处理授权？
- 四类授权的粒度、独立授予/撤回方式、有效期、说明版本和重新授权规则是什么？
- 现有缺少 Speaker / Consent 信息的历史 Message、Audio、Transcript 如何补录和使用？
- 撤回时正在采集、上传、STT、AI 处理或等待结果的任务如何停止，迟到结果如何处理？
- 历史内容隐藏范围如何覆盖 Owner、本人、普通协作者、列表、搜索、导出及派生内容？任务书确认的是先从其他协作者视角隐藏，其他访问边界仍需明确。
- 如何验证本人删除请求，如何处理多讲述者混合音频和多人来源 Memory，拆分/重生成后是否需要重新审查？
- 正常产品路径移除后，原始数据、可识别派生内容、对象存储、第三方副本、审计记录及备份分别何时清除？备份最终清除周期和可能的保留例外如何确定？
- 恢复系统备份时如何保持已删除或撤回内容的访问限制，避免普通产品路径再次出现相关内容？

## Related Documents

- [ADR-002 User账号删除策略](<ADR-002 User账号删除策略.md>)
- [ADR-003 Family 档案删除策略](<ADR-003 Family档案删除策略.md>)
- [ADR-004 Family 协作权限模型](<ADR-004 Family协作权限模型.md>)
- [ADR-005 Interview 参与者与讲述者模型](<ADR-005 Interview参与者与讲述者模型.md>)
- [ADR-008 MemoryCandidate 确认流程](<ADR-008 MemoryCandidate确认流程.md>)
- [ADR-009 AI-STT 第三方数据处理边界](<ADR-009 AI-STT第三方数据处理边界.md>)
- [Audio/STT 数据模型基线](../../02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [Memory 生成链路](../../04_AI设计/Memory生成链路设计_V1.0.md)

## Related Code

- [Family Model](../../../apps/backend/app/models/family.py)
- [FamilyMember Model](../../../apps/backend/app/models/family_member.py)
- [Interview Model](../../../apps/backend/app/models/interview.py)
- [InterviewMessage Model](../../../apps/backend/app/models/interview_message.py)
- [TranscriptSegment Model](../../../apps/backend/app/models/transcript_segment.py)
- [Audio Service](../../../apps/backend/app/services/audio_recording.py)
- [Transcript Service](../../../apps/backend/app/services/transcript.py)
- [Message Service](../../../apps/backend/app/services/interview_message.py)

## Revision History

| 日期 | 修订 |
| --- | --- |
| 2026-10-05 | Part 9.5.5-A：记录已确认的授权、撤回和删除约束；具体结构与流程保持 Proposed，未修改代码或数据库。 |
