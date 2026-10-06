# ADR-008 MemoryCandidate 确认流程

## Status

Proposed

Part 9.5.5-C 已冻结 Owner 最终确认、协作者逐版本审批、当前 Consent 门禁、来源恢复后重新审批的边界，见 [Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)。MemoryCandidate / Memory 的完整业务数据结构、提取与审查流程仍属于 Part 9.6，ADR 保持 Proposed。设计合同尚未实现。

## Context

Part 9.6 计划从访谈来源内容提取结构化回忆，再用于人生回忆录。AI 输出可能误解人物、时间、情感或叙述语气，因此提取结果必须保留来源并经过人工审查；仅凭 AI 输出不能认定为最终人生事实。

来源可能是讲述者回忆中的主观感受，也可能包含不确定或相互矛盾的叙述。确认过程应支持人工整理并保留来源，不把“人工确认”写成对客观历史真实性的自动保证。

## Current Implementation

- Backend 已有 Interview、Session、InterviewMessage、AudioRecording、Transcript、TranscriptSegment 模型及相应 API，没有 MemoryCandidate、Memory、提取作业或人工确认 API。
- 客户端 Message 创建 Schema 限制 `role=user, source=text`；服务端存在 `create_transcript_message` 辅助函数，可从 Segment 写入 `source=audio_transcript` 的 Message。该函数不代表完整 STT Pipeline 已接通。
- Message 是目标提取输入，可通过可空 `transcript_segment_id` 回链到 Segment、Transcript 和 Audio；文本 Message 没有音频分段来源。Segment 删除会将回链设为 NULL，来源删除如何影响未来 Candidate / Memory 尚未实现。
- Message 和 Segment 的自动序号当前使用 `max(sequence)+1`，数据库没有对应复合序号唯一约束；并发情况下不能保证目标提取输入顺序稳定。
- `FamilyMember` 表示回忆对象；Message 尚无真实讲述者关联，Segment 的 `speaker` 仅为字符串。C2A FamilyMembership 已实现；InterviewParticipant 和 Consent 尚未实现。
- `services/ai-service/` 没有实际 AI Service 实现，外部 Provider 未接入。Memory 生成链路文档是 Target Design，不是当前功能交付。

## Proposed Decision

### Target Design

```text
Source Message / Segment
        ↓
AI Extraction
        ↓
MemoryCandidate
        ↓
Human Review
      ↙        ↘
 rejected    confirmed
                ↓
              Memory
```

Backend 负责资源权限、授权检查、候选和确认后内容的业务存储；AI Service 负责提取。客户端向 Backend 表达审查意图，由 Service 校验访问权限和转换条件，再写入结果。上述 `rejected/confirmed` 是流程语义，不在本轮冻结数据库枚举或 API。

Candidate 应能追踪到所用 Message，存在音频来源时继续回链 Segment、Transcript、Audio 和时间范围；同时区分回忆对象与实际讲述者。目标需要保存来源、提取过程与人工修订之间的关系，不通过改写原 Message / Segment 代替候选编辑。

提取模型、提示词/提取版本、源内容范围及人工修改的记录方式属于待设计的可追溯能力。AI 重跑是否新建版本、如何与人工修订合并、是否保留旧候选，尚未决定；不得默认为覆盖已确认 Memory。

Owner 最终批准 Candidate 后才进入正式 Memory；Speaker 和 Collaborator 可以提交纠错或修订意见。历史来源恢复后需重新核验，必要时重生成衍生物，正式 Memory 必须重新经过 Owner 审批；旧审批不能绕过当前 Consent。后续 Memoir / RAG 的完整业务流程仍在 Part 9.6+ 设计范围。

## Decision Constraints

- 本轮任务要求 AI 生成的是 Candidate，不能绕过 Human Review 直接作为最终人生事实或已确认 Memory。
- 必须保留来源追踪，使整理结果可以查看原文；有音频来源时，应支持沿分段关系定位原音。
- 已确认一个 Interview 只有一个主要 subject，可以有多个 speaker / participant；不能把 FamilyMember、登录 User 或 `role=user` 当作同一个真实讲述者身份。
- 已冻结协作者对已有内容每次提交不可变的新版本，Owner 逐版本审批后生效；Owner 最终批准 Candidate 成为正式 Memory，Speaker / Collaborator 可提交纠错。审批不覆盖原文，不代替本人 Consent 或删除权。
- 已确认实际讲述者须同意 AI 分析和 Family 共享，并可以有效撤回/删除本人来源及可识别派生内容。确认后的 Memory 不因此免于这些约束，Owner 不得否决本人有效删除请求。
- 产品要求尽量保留讲述者情感态度、风格和原意，不无端虚构补充情节，并保存原文供后续人工修订。当前没有实现或验证该生成能力。

## Consequences

### Positive

- 将 AI 提取与人工确认分开，避免提取错误直接进入已确认回忆内容。
- 保留从候选、修订结果到原讲述的来源链，便于理解情感、纠错和后续润色。
- 为多人来源的撤回/删除提供影响范围识别的基础。

### Negative / Trade-offs

- 人工审查增加操作步骤，需要明确审查者权限及协作审批关系。
- 重跑、人工修订和来源删除会引入版本与一致性问题。
- 当前来源身份、Consent 和并发序号均有缺口，不能只新增 Candidate 表就宣称端到端提取完成。

## Security & Privacy Impact

提取前应检查 Family 权限和来源讲述者的 AI 处理授权；家庭共享另受相应用途授权约束。候选内容仍可能包含敏感信息，必须受同等访问边界控制，不能因“未确认”而公开给无权限者。

审查权、编辑权和数据删除权需要分别定义。来源撤回/删除时，相关 Candidate、Memory 及未来搜索/派生副本如何隐藏、删除或重生成，按 ADR-006 的已确认原则设计；具体算法尚未实现。

## Migration Impact

本轮没有创建 MemoryCandidate / Memory 模型、Schema、Service、API 或 Alembic 迁移。C 已冻结通用 SourceArtifact / DerivedSource / ArtifactContribution、RevisionProposal 和恢复后审批合同，供 Part 9.6+ 接入；Candidate / Memory 的完整业务字段、提取与重跑规则仍需在 Part 9.6 设计。

已有 Message 不能自动迁移为“已确认 Memory”；缺少讲述者和授权证据的历史来源也不能自动认定可用于 AI 提取。序号并发风险需要在提取依赖确定输入顺序前单独处理。

## Open Questions

- 多个讲述者对同一候选有不同意见时，审查界面如何保存和展示不同版本或不确定叙述？Owner 的最终批准权已冻结，不能代替事实核验。
- AI 重跑采用新版本、覆盖还是合并策略？如何保护人工修订和已确认 Memory，并处理重复候选？
- Human Review 的必填内容、允许的退回/拒绝/再编辑操作及完整状态转换有哪些？
- 一次提取使用哪些来源、提取范围与消息顺序如何界定，提取失败/重试如何避免重复写入？
- 混合多人来源 Candidate / Memory 的可靠拆分或重生成算法与验收如何落地？C 已冻结隔离、净化失败删除、当前授权门禁及正式 Memory 重新审批，算法尚未实现。
- 生产 Policy 的实际保留期限与 Provider / Storage / Backup 能力待单独确认；最小化 Ledger 与来源删除传播合同已在 C 冻结。

## Related Documents

- [Memory 生成链路设计](../../04_AI设计/Memory生成链路设计_V1.0.md)
- [Message 事件模型设计](../../03_业务流程/Message事件模型设计_V1.0.md)
- [Audio/STT 数据模型基线](../../02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [技术债登记表](../../06_技术决策记录/技术债登记表_V1.0.md)
- [ADR-001 Segment-Message 关系](<ADR-001 Segment-Message关系.md>)
- [ADR-004 Family 协作权限模型](<ADR-004 Family协作权限模型.md>)
- [ADR-005 Interview 参与者与讲述者模型](<ADR-005 Interview参与者与讲述者模型.md>)
- [ADR-006 Consent 授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)
- [ADR-009 AI-STT 第三方数据处理边界](<ADR-009 AI-STT第三方数据处理边界.md>)

## Related Code

- [InterviewMessage Model](../../../apps/backend/app/models/interview_message.py)
- [TranscriptSegment Model](../../../apps/backend/app/models/transcript_segment.py)
- [Message Schema](../../../apps/backend/app/schemas/interview_message.py)
- [Message Service](../../../apps/backend/app/services/interview_message.py)
- [Message CRUD](../../../apps/backend/app/crud/interview_message.py)
- [Segment Service](../../../apps/backend/app/services/transcript_segment.py)
- [Sessions API](../../../apps/backend/app/api/v1/sessions.py)
- [AI Service 目录（当前占位）](../../../services/ai-service/)

## Revision History

| 日期 | 修订 |
| --- | --- |
| 2026-10-05 | Part 9.5.5-A：记录候选提取、人工审查和来源边界；确认权限、版本与完整流程保持 Proposed，未实现 Memory 功能。 |
| 2026-10-05 | Part 9.5.5-C：引用已冻结的 Owner 确认、逐版本审批与来源恢复合同；Part 9.6 业务结构/流程仍 Proposed，未实现 Memory 功能。 |
