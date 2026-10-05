# ADR-005 Interview参与者与讲述者模型

## Status

Proposed

一个 Interview 有一个主要回忆对象、可以有多个讲述者的产品原则已确认。参与者最小基数、身份映射、来源归属和实际模型结构尚未冻结。

## Context

“回忆我自己”需要知道登录用户对应哪位档案人物；代为讲述亲人的经历时，故事对象与实际讲述者又可能不同。多人补充同一人物的回忆，还需要将每份来源归属到实际讲述者，才能判断本人授权、撤回、删除和派生 Memory 的来源。

不能根据 Interview 的 FamilyMember 或 API 调用者就推定全部原话由该人物或该账号本人讲述，也不能用 STT 的字符串 speaker 标签代替经确认的人的身份。

## Current Implementation

- `User` 是 JWT 认证的登录账号；没有“本人 FamilyMember”关联。
- `FamilyMember` 是归属于 Family 的档案人物，当前字段不包含 User、Membership 或 Participant 身份关系。
- `Interview.family_member_id` 为非空外键，一个 Interview 当前关联一个 FamilyMember；这是回忆对象关系，没有独立 Participant 集合。
- Session 只关联 Interview。Message 只关联 Session，并具有 `role`、`source` 和可空的 `transcript_segment_id`；没有实际讲述者字段。
- Message 的 `role=user` 表示消息角色，不能确定是哪位人类讲述。客户端文本输入仅允许 `user/text`；服务端可从 Segment 创建 `user/audio_transcript` 消息。
- `TranscriptSegment.speaker` 是可空的普通字符串，创建 Schema 接受该标签。它不是 User 或 Participant 外键，也不是经过验证的授权主体。
- 当前没有 FamilyMembership、InterviewParticipant、讲述者身份核验、Consent 或多人来源 Memory 实现。

## Proposed Decision

### Target Design

继续保持一个 Interview 对应一个主要回忆对象，同时独立表达实际参与讲述的人。概念边界如下：

| 概念 | 含义 | 是否已实现 |
| --- | --- | --- |
| User | 登录账号，JWT 身份主体 | 已实现 |
| Family | 家庭档案归属范围，当前由 Owner 持有 | 已实现 |
| FamilyMember | 回忆档案中的人物，可作为 Interview 的主要回忆对象 | 已实现 |
| FamilyMembership | User 与 Family 的访问关系 | 目标概念，未实现 |
| Interview subject | Interview 的主要回忆对象；当前由 `family_member_id` 表达 | 单一对象关系已实现 |
| Interview participant / speaker | 实际参与或讲述的人；实际讲述者的来源与 Consent 需可识别 | 目标概念，未实现 |

一个 Interview 可以包含多个实际讲述者。最终采用 `0..N` 还是 `1..N` 的参与者最小基数尚未决定，也可能需要分别讨论草稿创建阶段与实际采集阶段。本 ADR 不冻结该基数。

参与者与 User、FamilyMember、Membership 之间是否关联、如何关联及有无账号的讲述者如何表示，需要后续决定。这里的概念区分不要求每种概念立即建成一张表，也不批准具体数据库结构。

### Product Decision

默认入口为“回忆我自己”，仍使用 Family / FamilyMember / Interview 统一模型，不另建独立个人档案系统。也支持实际讲述者讲述其他人的经历，以及多人讲述同一 subject。

## Decision Constraints

1. 一个 Interview 只有一个主要 subject；可以有多个实际 speaker / participant。
2. FamilyMember 不能直接等同于登录 User、Family Collaborator 或实际 Speaker。
3. Subject 与 Speaker 可以是同一个人，也可以不同；“回忆我自己”需要明确身份映射，不能根据姓名自动认定。
4. FamilyMembership 表达访问关系，Participant/Speaker 表达参与或讲述关系；成为讲述者不自动成为 Collaborator，成为 Collaborator 不自动成为某段来源的讲述者。
5. 实际讲述者须本人同意录音、转写、AI 分析和 Family 共享；Owner 不能代替具有自主决定能力的成年讲述者同意。
6. 本人有效撤回/删除请求需要定位本人来源及可识别派生内容。多人来源 Memory 的拆分/重生成算法未实现。
7. `role=user`、客户端传入的身份或 STT speaker 标签不能单独作为本人身份及 Consent 已成立的证据。
8. 保留来源原文以供追溯和人工修订；讲述者身份不可因 AI 生成或整理而被无依据地替换。

## Consequences

### Positive

- 同一领域模型支持本人回忆、他人代述和多人补充，不需要复制一套个人档案模块。
- 回忆对象与原话讲述者分开，便于保留叙述者的情感、态度和来源。
- 后续 Consent、删除与 Memory 审核可以依据实际来源判断，而非误用 Owner 或 subject 身份。

### Negative / Trade-offs

- 需要处理无账号讲述者、账号与人物映射及匿名 STT 标签的身份确认；当前模型没有这些能力。
- 历史 Message / Segment 缺少可验证的讲述者归属，不能无依据地回填为 Owner 或 subject。
- 多人同段、重叠发言、后续身份更正会增加来源记录和派生内容重算的复杂度。

## Security & Privacy Impact

实际讲述者的身份和 Family 访问权限必须分别校验。知道某人的名字或成为采访参与者，不能据此访问该 Family 全部档案。讲述者的 Consent 也不能代替 Family 对调用者的访问许可。

未来来源处理需避免把未经确认的 STT 标签当作本人授权依据。对身份未知、身份冲突或缺少同意记录的历史资料如何处理必须先决定，不能默认具有授权或默认是 Owner 的贡献。

## Migration Impact

本轮不创建 Participant Model，不修改 `family_member_id`、Message、Segment、Schema、Service 或 API，不创建和执行 migration。

未来落地需要单独确定身份关系与来源关联方式，并审查现有 Interview、Message、Segment 的回填条件。没有证据的历史讲述者信息应作为未决数据处理问题，不得自动推定和迁移。

## Open Questions

- Participant 的最小基数是 `0..N` 还是 `1..N`？草稿创建与真实采集是否采用不同要求？
- 无账号讲述者如何表示、验证身份和本人同意？Participant 是否必须或可选关联 User / FamilyMember？
- “回忆我自己”如何建立或确认 User 与 FamilyMember 的本人映射？如何防止重复人物和误认？
- Participant 与 Speaker 是否需要进一步区分采访者、陪同者和实际发言者？
- Message、Audio、Transcript、Segment 各自如何表达来源归属？多人同段或重叠发言如何处理？
- STT speaker 标签如何与经确认的实际讲述者关联，谁可以更正该关联？
- 缺少讲述者身份和 Consent 的历史数据能否进入 Part 9.6 提取，补充核验方式是什么？
- Subject 与 Speaker 是否拥有 Candidate 确认或纠错权限？与 Family Collaborator 权限如何配合？

## Related Documents

- [系统架构总览](../../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型设计基线](../../02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [Message 事件模型设计](../../03_业务流程/Message事件模型设计_V1.0.md)
- [Memory 生成链路设计](../../04_AI设计/Memory生成链路设计_V1.0.md)
- [ADR-004 Family协作权限模型](<ADR-004 Family协作权限模型.md>)
- [ADR-006 Consent授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)
- [ADR-008 MemoryCandidate确认流程](<ADR-008 MemoryCandidate确认流程.md>)

## Related Code

- [User Model](../../../apps/backend/app/models/user.py)、[FamilyMember Model](../../../apps/backend/app/models/family_member.py)、[Interview Model](../../../apps/backend/app/models/interview.py)
- [Message Model](../../../apps/backend/app/models/interview_message.py)、[Segment Model](../../../apps/backend/app/models/transcript_segment.py)
- [FamilyMember Schema](../../../apps/backend/app/schemas/family_member.py)、[Interview Schema](../../../apps/backend/app/schemas/interview.py)、[Message Schema](../../../apps/backend/app/schemas/interview_message.py)、[Segment Schema](../../../apps/backend/app/schemas/transcript_segment.py)
- [Interview Service](../../../apps/backend/app/services/interview.py)、[Message Service](../../../apps/backend/app/services/interview_message.py)
- [Interview API](../../../apps/backend/app/api/v1/interviews.py)、[FamilyMember API](../../../apps/backend/app/api/v1/family_members.py)

## Revision History

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-10-05 | V1.0 | Part 9.5.5-A；区分账号、档案人物、访问关系和实际讲述者，记录已确认产品约束，保留基数与来源身份结构的未决项。 |
