# ADR-008 MemoryCandidate 确认流程

## Status

Proposed

2026-10-14 最新实现事实：9.6-B 的 offline_memory.v1 单一 RevisionProposal profile 已获授权并写入工作区，支持不可变 Revision、Owner 精确版本批准及 Memoir 快照，尚未提交。独立实现复核 PASS WITH FINDINGS，B-IR-01～04 CLOSED；HTTP15/PG16.15 28/Legacy18脚本场景在各自范围通过，57项全覆盖未完成。详情见 [独立闭环复核报告](../../05_开发阶段记录/Part9.6-B_Validation-Closure_Independent-Review_2026-10-14.md)。ADR整体继续Proposed：生产Artifact/Consent/C5/C6接线与完整验收仍未完成；下方此前基线和草案记录保留作历史追溯。

Part 9.5.5-C 已冻结 Owner 最终确认、协作者逐版本审批、当前 Consent 门禁、来源恢复后重新审批的边界，见 [Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)。9.6-B 的产品范围已确认，完整工程草案已归档，见 [Candidate / Revision / Human Review Contract V1.0](../../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。ADR 保持 Proposed；归档不是 Design Freeze、实施批准或功能完成。

## Context

Part 9.6 计划从访谈来源内容提取结构化回忆，再用于人生回忆录。AI 输出可能误解人物、时间、情感或叙述语气，因此提取结果必须保留来源并经过人工审查；仅凭 AI 输出不能认定为最终人生事实。

来源可能是讲述者回忆中的主观感受，也可能包含不确定或相互矛盾的叙述。确认过程应支持人工整理并保留来源，不把“人工确认”写成对客观历史真实性的自动保证。

## Current Implementation

- 当前基线 master @ `6c12e96e4f83ada7cb7c7dd60fec4283269f8700` 已有上述 Backend 模型/API，以及人工 Memory 与确定性 Memoir 草稿 Slice 1；没有 MemoryCandidate、不可变 Revision、正式审批或 Memory AI 提取 API。
- 客户端 Message 创建 Schema 限制 `role=user, source=text`；服务端存在 `create_transcript_message` 辅助函数，可从 Segment 写入 `source=audio_transcript` 的 Message。该函数不代表完整 STT Pipeline 已接通。
- Message 是目标提取输入，可通过可空 `transcript_segment_id` 回链到 Segment、Transcript 和 Audio；文本 Message 没有音频分段来源。Segment 删除会将回链设为 NULL，来源删除如何影响未来 Candidate / Memory 尚未实现。
- 9.6-A 源码已对三个 Message 写入入口采用 Session 级协调，并添加 `UNIQUE(session_id,sequence)` ORM / migration 源码；真实 PostgreSQL 迁移及并发尚未验证。Segment 并发及完整 C3 guards 不因 B 设计完成。B 首版指定一个不可变 Message ID，不依赖跨消息提取顺序。
- `FamilyMember` 表示回忆对象；Message 尚无真实讲述者关联，Segment 的 `speaker` 仅为字符串。C2A FamilyMembership 已实现并封板；C2B InterviewParticipant 身份基础已实施并封板；Consent 与 SourceSpeakerBinding 尚未实现。
- `services/ai-service/` 已有离线 Interview Agent 与 Mock Provider Contract；外部 Provider、Memory 提取、真实跨服务 transport 未接入。Memory 生成链路文档仍区分 Target Design 与已交付人工 Slice。

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

Backend 负责资源权限、授权检查、候选和确认后内容的业务存储；AI Service 负责提取。客户端向 Backend 表达审查意图，由 Service 校验访问权限和转换条件，再写入结果。上述 `rejected/confirmed` 是早期流程语义。9.6-B 详细草案以唯一 RevisionProposal 的状态/精确版本审批为准，不设置第二 Candidate confirmed 权威；人工与 AI 草稿均需明确 Owner 批准。

Candidate 应能追踪到所用 Message，存在音频来源时继续回链 Segment、Transcript、Audio 和时间范围；同时区分回忆对象与实际讲述者。目标需要保存来源、提取过程与人工修订之间的关系，不通过改写原 Message / Segment 代替候选编辑。

提取模型、提示词/提取版本、源内容范围及人工修改的记录方式属于待设计的可追溯能力。已确认重跑新建提取批次与新 Candidate，不自动匹配、合并或覆盖；每次提取只选一条 user/text Message、输出零至多个候选。Candidate 批准只创建新 Memory；已有 Memory 修改走人工 Revision。详细 API/状态/约束以 9.6-B 草案为待审 SSOT。

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

本轮没有创建 MemoryCandidate / Revision / Proposal 模型、Schema、Service、API 或 Alembic 迁移；人工 Memory / Memoir 已由先前 Slice 1 实现。C 已冻结通用 SourceArtifact / DerivedSource / ArtifactContribution、RevisionProposal 和恢复后审批合同，供 Part 9.6+ 接入；9.6-B 以 offline_memory.v1 业务 Revision FK profile 衔接同一 C5 状态机，后续原地接入 Artifact，不生成假 Artifact 或第二审批体系。表结构、API、Legacy 迁移及验收详见 9.6-B 工程草案，已完成正式独立审查 PASS WITH FINDINGS，工程修订待定向再审。

已有 Message 不能自动迁移为“已确认 Memory”；缺少讲述者和授权证据的历史来源也不能自动认定可用于 AI 提取。序号并发风险需要在提取依赖确定输入顺序前单独处理。

## Open Questions

- 多个讲述者对同一候选有不同意见时，审查界面如何保存和展示不同版本或不确定叙述？Owner 的最终批准权已冻结，不能代替事实核验。
- 9.6-B 工程草案的字段/FK、七态 Proposal、API、幂等、迁移及验收已修订待定向再审；已确认单源、新批次、不可变修订、逐版本批准与精确 Memoir 引用，不再作为未决产品问题。
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
- [AI Service 目录（离线 Agent / Mock 范围）](../../../services/ai-service/)

## Revision History

| 日期 | 修订 |
| --- | --- |
| 2026-10-05 | Part 9.5.5-A：记录候选提取、人工审查和来源边界；确认权限、版本与完整流程保持 Proposed，未实现 Memory 功能。 |
| 2026-10-05 | Part 9.5.5-C：引用已冻结的 Owner 确认、逐版本审批与来源恢复合同；Part 9.6 业务结构/流程仍 Proposed，未实现 Memory 功能。 |


## 9.6-B 当前设计状态（2026-10-12）

详细 SSOT：[Candidate + Immutable Revision + Human Review Contract V1.0](../../04_AI设计/Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。

产品决定 CONFIRMED；合同 REVISED DRAFT — PENDING TARGETED RE-REVIEW；Implementation NOT STARTED / NOT AUTHORIZED。新增人工和 AI 片段统一不可变 Revision＋明确 Owner 审批；Memoir pin 精确批准版本；历史 Memory/章节保留 Legacy，不补造身份/Consent/批准。此摘要不复制具体表或 API，不改变 C 已冻结的本人权利、删除或保留政策。

ADR-008 仍为 **Proposed**。本次仅修正文档中的实现事实并归档引用，不创建业务实现或 migration，不执行测试/数据库/Git写入。

## 9.6-B 工程修订状态（2026-10-12）

独立合同审查 PASS WITH FINDINGS；三项工程缺口已补入详细合同待定向再审。旧DELETE的引用冲突/回滚兼容不实现C6，也不改变Speaker本人权利；同步Stub只验TimeoutError分类，不提供五秒deadline保证。已有目标版本、新建例外和未知提交结局的只读恢复明确。

拟实施范围42个文件，57项未来验收。**Proposed / PENDING TARGETED RE-REVIEW / IMPLEMENTATION NOT AUTHORIZED**；不因修订自动Accepted、Design Frozen或启动代码。
