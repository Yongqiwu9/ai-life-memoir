# ADR-007 Interview-Session状态机

## Status

Proposed

本 ADR 记录实现与目标文档的冲突。目标枚举、转换条件和迁移策略尚未获产品负责人确认，不因本次文档整理成为 Accepted。

## Context

Part 9.6 Memory Extraction 将消费 InterviewSession 的 Message 流，需要清楚区分访谈进行状态、音频处理状态以及内容是否可处理。[Interview 生命周期设计](../../03_业务流程/Interview生命周期状态机设计_V1.0.md)提出的状态与 Part 9.4–9.5 代码不一致；真实上传、Object Storage、STT Provider 和 AI Pipeline 尚未实现。

状态字段存在不代表相应录音、转写或处理功能可用；状态完成也不能代替讲述者同意、访问授权或人工确认。

## Current Implementation

### 当前枚举和写入入口

| 对象 | 当前枚举 | 默认值 | 普通客户端实际可写入口 |
| --- | --- | --- | --- |
| Interview | `draft / in_progress / completed / cancelled` | Model 创建默认 `draft` | `PATCH /api/v1/interviews/{interview_id}` 的 `InterviewUpdate.status` |
| InterviewSession | `active / completed / cancelled` | Create Schema 与 Model 默认 `active` | `POST /api/v1/interviews/{interview_id}/sessions` 的 `InterviewSessionCreate.status` |
| AudioRecording | `pending / processing / completed / failed` | Create Schema 与 Model 默认 `pending` | `POST /api/v1/sessions/{session_id}/audios` 的 `AudioRecordingCreate.status` |
| Transcript | `pending / processing / completed / failed` | Create Schema 与 Model 默认 `pending` | `POST /api/v1/audios/{audio_id}/transcripts` 的 `TranscriptCreate.status` |

上述 API 有 JWT 和 Owner 归属检查，Schema 会限制枚举值，但没有状态转换规则。`interview_service.update_interview` 将客户端 `status.value` 写入 CRUD；Session、Audio、Transcript 的创建 Service 同样传递客户端提交的状态。枚举值合法不能证明转换合法或处理真实完成。

当前 Session、Audio、Transcript Router 没有对应状态更新 API或完整生命周期动作。创建 Session 不会推进 Interview 状态；创建 Message、Audio、Transcript、Segment 时也没有根据父对象当前状态判断是否允许操作。Message 的客户端 `role=user / source=text` 限制已经存在，但不等于会话状态机已实现。

### 时间字段与存储约束

- Interview 的 `started_at / completed_at`、Session 的 `started_at / ended_at`、Audio 的 `started_at / ended_at` 都是 nullable、timezone-aware 字段。当前 Service/CRUD 没有生命周期写入，是占位字段。
- `created_at / updated_at` 由数据库默认值和 ORM 更新规则维护，与访谈开始、结束、处理完成不是同一种时间。
- 当前 Transcript 没有 `started_at / ended_at` 字段，只有 `created_at / updated_at`，不能描述为已经记录 STT 处理耗时。
- 状态使用 `String(32)` 保存，现有 Model 和 migration 未建立状态 `CHECK` 约束；API 枚举限制并非数据库级状态约束。本次未连接数据库验证实际部署状态。

### 相邻技术债

Message 在普通文本写入和内部 `create_transcript_message` 中使用 `max(sequence) + 1`；Segment 接受客户端 `sequence`，未指定时同样使用 `max + 1`。当前没有 `(session_id, sequence)` 或 `(transcript_id, sequence)` 复合唯一约束。并发文本、STT 或后续 AI 写入可能使 Memory 输入重复或排序不稳定。

这些是 [TD-9.4-01、TD-9.4-02、TD-9.5-04](../技术债登记表_V1.0.md) 的现状，本轮不修复，不冻结锁、计数器、重试或具体数据库约束方案。[ADR-001](<ADR-001 Segment-Message关系.md>) 中一个 Segment 可关联多个 Message 的 Accepted 决策，不等于允许同一容器内重复序号，也不要求为 `transcript_segment_id` 增加唯一约束。

## Proposed Decision

### Target Design：待确认的目标

现有生命周期文档提出以下目标集合：

| 对象 | Current Implementation | Target Design（未 Accepted） |
| --- | --- | --- |
| Interview | `draft / in_progress / completed / cancelled` | `draft / active / completed / archived / cancelled` |
| Session | `active / completed / cancelled` | `created / recording / processing / completed / cancelled` |

目标文档描述 Interview 经 `draft → active → completed → archived` 推进，以及 Session 经 `created → recording → processing → completed` 推进，另有取消路径。文档开头和差异摘要有时省略 `cancelled`，但正文状态表包含该状态；本 ADR 展示完整提议，不将文档内的任何流程直接视为已确认。

`in_progress → active` 是否只是名称迁移、旧 Session `active` 对应哪种新状态、取消和归档是否为终态，都仍需明确。录音导向的 Session 目标还需要覆盖已存在的纯文本访谈；不得仅凭旧状态或 nullable 时间字段自动推断过去发生过录音。

### 拟采用的服务端控制原则

客户端表达开始、结束、取消、归档等操作意图；Service 根据认证身份、权限、当前状态和前置条件校验合法转换，再由 CRUD 持久化。普通客户端不应任意写内部处理状态。

Audio/Transcript 的处理状态原则上由服务端上传、转写、重试及错误处理流程维护。普通客户端提交 `completed` 不能作为上传成功或 STT 完成的证据。具体动作 API、事件机制、异常及重试规则需在后续实施设计中确定。

生命周期时间字段应随合法转换由服务端维护并使用 timezone-aware UTC；写入时机、重复请求行为与历史数据处理方式尚未冻结。状态转换和相关数据写入应有明确事务边界，但本 ADR 不选择实际并发或事务实现。

## Decision Constraints

以下为产品已确认的约束，不代表本 ADR 的目标状态表已经 Accepted：

- 一个 Interview 只有一个主要回忆对象，可以有多个实际讲述者；状态转换不能把 FamilyMember 当作讲述者身份或同意证据。
- 默认“回忆我自己”，使用统一 Family / FamilyMember / Interview 模型；支持文本与录音回忆场景，不得把 Session 的创建一律等同于开始录音。
- 实际讲述者须同意录音、转写、AI 分析和 Family 范围共享；Owner 不能替具有自主决定能力的成年讲述者同意。后续服务端处理必须尊重有效授权。
- 讲述者撤回后，针对其内容的后续录音、转写、AI 分析和 Family 共享必须停止；相关历史内容先对其他协作者隐藏。状态为 `active / processing / completed` 不能覆盖撤回约束。
- 删除的数据立即从正常产品访问路径移除，Owner 不提供普通恢复入口。`archived` 的目标含义不得与删除或撤回混淆；备份清除周期和物理删除时间仍未确定。
- 已确认首版 Family 协作方向；状态操作权限的细分尚未确认，不能自动将现有 Owner-only 校验当作最终规则。

## Consequences

### Positive

区分实际 API 能力与目标状态机，防止后续 Memory 提取将客户端提交的处理完成状态当作可信证据。服务端校验转换有助于使权限、授权、时间字段与处理结果保持一致。

### Negative / Trade-offs

目标状态落地可能改变 API 请求方式和历史数据含义；必须先解决纯文本 Session、处理中取消、多音频/多次转写完成条件等问题。当前代码仍保留直接状态输入，本 ADR 不能代替实现或验收。

## Security & Privacy Impact

Owner 归属校验能限制当前访问范围，但不能防止获准用户伪造内部处理完成状态。后续 Service 需要把资源权限与 Consent 分开检查，并考虑撤回/删除与处理中任务竞态，防止已禁止的数据被任务结果重新发布。

状态为 `completed` 不代表资料已获 Family 共享授权，也不代表 Candidate 经人工确认成为最终 Memory。

## Migration Impact

本轮无代码、Schema、Service、Router、测试或 migration 改动，不执行数据库命令。后续状态落地若改变存量值、约束或时间语义，必须通过 Alembic，并先核查实际数据、明确映射与兼容策略，再验证迁移；不得直接将所有旧 `active` Session 回填成 `recording`。

sequence 风险保持开放，不在本轮增加约束或修改分配算法。真实上传和 STT 仍需独立实施范围。

## Open Questions

1. 是否采用目标状态集合？`in_progress` 是否改为 `active`；Interview 的 `archived` 是否终态、能否恢复；各取消路径如何定义？
2. 纯文本 Session 如何进入、推进和结束？是否需要与录音 Session 区分流程，或调整目标枚举？
3. 什么条件使 Session 和 Interview 完成？同一 Session 多音频、多 Transcript 重试、仍在处理的内容如何影响完成和 Memory 提取资格？
4. 谁可以开始、结束、取消、归档或重开？Family 协作者的操作如何受 Owner 同意规则约束？
5. 处理中取消、失败、重试、撤回和删除如何交互？在途任务的结果如何避免恢复已隐藏或删除的内容？
6. 时间字段的准确含义、写入时机、重复请求和历史值缺失如何处理？需不需要额外处理时间字段？
7. 旧状态映射、API 兼容、数据库约束、事务和并发控制采用什么实施方案？Message/Segment 序号问题在 Part 9.6 前如何验收？
8. Memory 提取是否允许在活跃 Session 中增量运行，还是仅处理已结束的稳定输入？资格规则与授权、来源版本如何一起校验？

## Related Documents

- [系统架构总览](../../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型基线](../../02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [Interview 生命周期状态机设计](../../03_业务流程/Interview生命周期状态机设计_V1.0.md)
- [Message 事件模型设计](../../03_业务流程/Message事件模型设计_V1.0.md)
- [Memory 生成链路设计](../../04_AI设计/Memory生成链路设计_V1.0.md)
- [Part 开发路线图](../../05_开发阶段记录/Part开发路线图_V2.0.md)
- [技术债登记表](../技术债登记表_V1.0.md)
- [ADR-001 Segment-Message 关系](<ADR-001 Segment-Message关系.md>)
- [ADR-004 Family 协作权限](ADR-004%20Family协作权限模型.md)
- [ADR-005 Interview 参与者与讲述者](ADR-005%20Interview参与者与讲述者模型.md)
- [ADR-006 Consent 授权撤回与删除](ADR-006%20Consent授权撤回与删除策略.md)
- [ADR-008 MemoryCandidate 确认流程](ADR-008%20MemoryCandidate确认流程.md)

## Related Code

- [状态枚举](../../../apps/backend/app/models/enums.py)
- Model：[Interview](../../../apps/backend/app/models/interview.py)、[Session](../../../apps/backend/app/models/interview_session.py)、[Audio](../../../apps/backend/app/models/audio_recording.py)、[Transcript](../../../apps/backend/app/models/transcript.py)
- Schema：[Interview](../../../apps/backend/app/schemas/interview.py)、[Session](../../../apps/backend/app/schemas/interview_session.py)、[Audio](../../../apps/backend/app/schemas/audio_recording.py)、[Transcript](../../../apps/backend/app/schemas/transcript.py)
- Service：[Interview](../../../apps/backend/app/services/interview.py)、[Session](../../../apps/backend/app/services/interview_session.py)、[Audio](../../../apps/backend/app/services/audio_recording.py)、[Transcript](../../../apps/backend/app/services/transcript.py)
- Router：[Interview/Session 创建](../../../apps/backend/app/api/v1/interviews.py)、[Session/Message](../../../apps/backend/app/api/v1/sessions.py)、[Audio/Transcript 创建](../../../apps/backend/app/api/v1/audios.py)、[Transcript/Segment](../../../apps/backend/app/api/v1/transcripts.py)
- 序号：[Message Service](../../../apps/backend/app/services/interview_message.py)、[Message CRUD](../../../apps/backend/app/crud/interview_message.py)、[Segment Schema](../../../apps/backend/app/schemas/transcript_segment.py)、[Segment Service](../../../apps/backend/app/services/transcript_segment.py)、[Segment CRUD](../../../apps/backend/app/crud/transcript_segment.py)

## Revision History

| 日期 | 变更 | 状态 |
| --- | --- | --- |
| 2026-10-05 | Part 9.5.5-A：基于代码记录当前状态、客户端入口与目标冲突，整理产品约束和待决问题；未实施状态机 | Proposed |
