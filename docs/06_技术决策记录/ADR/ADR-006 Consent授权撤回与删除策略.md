# ADR-006 Consent 授权、撤回与删除策略

## Status

Accepted

Implementation: Not Started

本 ADR 摘要记录 Part 9.5.5-C 已冻结的 Consent、用途分支、撤回、历史恢复、净化、删除传播、备份恢复和 Policy 合同。完整表结构、状态机、API 合同、迁移顺序与验收矩阵以 [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md) 为唯一事实来源。Accepted 表示设计已冻结，不表示功能已经实现。

## Context

真实 Speaker 可能与登录账号能力、Family Owner、Interview subject 或实际 operator 不同。Family 访问权限不能替代 Speaker 对本人来源的处理授权；撤回用途、请求删除本人来源、Owner 删除整个 Family Archive 和 User Account 删除也是不同生命周期。

## Current Implementation

- 当前资源访问通过 `Family.owner_id` 沿 Interview / Session / Audio / Transcript 等关系校验 Owner；尚无 FamilyMembership、InterviewParticipant、SourceSpeakerBinding 或 Consent 模型/API。
- `Interview.family_member_id` 指向回忆对象。`InterviewMessage.role=user` 只表示消息角色；`TranscriptSegment.speaker` 是可空字符串，均不能作为本人身份或授权证据。
- AudioRecording、Transcript、TranscriptSegment 只有元数据模型/API。没有真实录音上传、对象存储、外部 STT、AI Pipeline、撤回处理或本人来源删除流程。
- Message 可通过 `transcript_segment_id` 回链 Segment；该外键为 `ON DELETE SET NULL`，删除 Segment 不会删除 Message 正文副本。
- 当前 Family 删除依赖直接删除及数据库级联，没有声明范围、逐目标核验、第三方/备份阶段、最小 Ledger 或恢复隔离重放能力。

## Decision

### Consent 模型

- Consent 按 recording、transcription、ai_analysis、family_share 四个用途独立授予和撤回。family_share 进一步区分 text_derived 与 raw_audio；普通 Collaborator 播放原音还需要明确 raw_audio 许可。
- ConsentGrant 是 InterviewParticipant、用途和类别的当前投影；ConsentEvent 是不可改写的本人授权历史。有效 Grant 可以供同一 Interview 的新 Session 和新 Source 使用。
- SourceConsentBinding 固定记录某个 SourceSpeakerBinding 使用的授权 epoch。Source-specific restriction 高于 Interview allow；re-consent 产生新 epoch，不批量重绑历史 Source。
- 原始文字以本人提交或确认归档及适用保存告知为依据，不要求不存在的“文字录音授权”。
- 有效 Consent 要求即时本人手机或邮箱验证、成年自主决定声明、本人 Participant / Source 归属确认，以及对明确 PrivacyPolicyVersion 和告知内容的主动授权。
- operator 可以提出操作与绑定意图，不能代替自主成年 Speaker 成为 consenter；Owner 也不能代为授权。

### 撤回与历史恢复

- 用途撤回立即阻止未来处理和分享，并将对应历史产物及依赖置为 Restricted / Quarantined。Owner、Collaborator、搜索、导出、AI 输入和派生读取都受同一门禁。
- 撤回不自动等于立即物理删除。到预先告知的最长隔离保留期时，默认进入对应 Source / Speaker / purpose/category 的 DeletionPipeline；只有本人在到期前完成明确的对应 Source 与用途恢复，才可取消尚未受理的该分支删除。
- 一个用途撤回、恢复或到期清理，不改变其他独立用途的状态。共用物理对象仍有独立有效保留依据时，可以受限保存；撤回用途的分支和副本仍须清除。
- re-consent 只更新 Interview 当前授权。恢复历史 Source 必须由本人明确选择 Source、用途和分享类别，重新核验身份、归属、Policy、当前 generation 及全部必要用途。
- `deletion_pending` / `erased` 范围不得恢复。历史 Source 恢复后，衍生版本必须重新核验并在必要时重生成；旧 Memory 审批不自动恢复，必须重新由 Owner 审批。
- 历史来源缺少可核验身份或 Consent 时，Owner 也只能看到必要状态；核验本人身份、来源归属及相应用途授权后，才可进入明确的恢复流程。新授权不得倒填为历史录音发生时已经授权。

### 删除、净化与派生传播

- Speaker 可以请求删除本人 Audio、Transcript、Message/source data 及可识别派生内容，Owner 不得阻止或撤销。Owner 可以独立请求删除整个 Family Archive；该权限不构成代替 Speaker Consent。
- 删除流程按声明范围建立 DeletionRequest / DeletionTarget，至少区分隔离、在线、衍生、第三方、备份和声明范围完成阶段。只有全部已声明目标达到 verified 或 not_applicable_verified，才能进入最终完成；pending、blocked 或 verification_unknown 不能报告完成。
- 删除受理与普通访问隔离必须同事务生效。重试不得扩张范围、回退已完成目标或延长已承诺期限；净化尝试也不能延迟原件适用的删除上限。
- 混合来源删除时先隔离整份来源。V1 只允许按已确认 Speaker / Segment 净化，不开放任意文本片段级授权。能够可靠分离时，创建全新来源版本并重新登记剩余 Speaker、用途限制和 Provenance；原混合文件及受污染旧版本继续删除。
- 净化版本只有在系统技术检查通过且每位剩余 Speaker 确认自己的保留贡献后，才可发布或使用。确认仅决定净化版本是否发布，不得拖延原件删除；残留、未知、重叠无法可靠处理、任一拒绝、未确认超过窗口或其他验收失败，都放弃净化并整份删除。
- 被可靠移除 Speaker 的内容贡献不传播到净化版本；其他 Speaker 的 source-specific deny、用途限制和授权历史继续继承。新文件 UUID 不能绕过旧来源限制。
- 每个正文对象、复制关系、Speaker 贡献及外部副本必须通过 SourceArtifact、ArtifactContribution 和 DerivedSource 登记。Message 的可空 Segment FK 不承担删除传播；Segment 删除后仍须定位并清除 Message 正文副本。

### Policy、备份与恢复

- 清除期限、隔离期、净化窗口、重试上限和 Ledger / 证据保留期由发布后的 PrivacyPolicyVersion 提供，本 ADR 不冻结具体数值。配置更新不得延长已向 Speaker 承诺的期限。
- active Policy 缺少必要值或能力验证时，禁止新采集、有效授权签署、历史恢复、净化发布和外部处理；Withdrawal / Deletion 仍受理并立即隔离，能确定完成的清理继续执行，未知目标保持 blocked / unknown。
- 使用滚动备份和不含正文的最小 DeletionLedger。备份恢复必须先进入隔离环境，载入可信最新 Ledger 与当前限制控制记录，重放门禁和清理并核验来源闭包后才可开放。只有旧备份而没有最新控制记录时，不得恢复成普通服务。

## Consequences

### Positive

- Family 权限、本人 Consent、Source override、删除和派生传播形成同一 fail-closed 门禁。
- epoch 与明确恢复阻止 Interview re-consent 自动重新开放旧 Source。
- 逐目标删除、最小 Ledger 和隔离恢复避免把数据库级联、排队状态或备份过期误报为完成。

### Trade-offs

- 所有读取、搜索、导出、AI/STT、审批、回调和派生写入都必须重查当前 generation、Consent 和删除状态。
- 多 Speaker 来源需要完整归属、净化验收和删除闭包；无法可靠分离时会删除整份来源。
- 第三方、对象存储、缓存、向量、导出和备份均需要登记与清理适配器，未验证能力不能启用真实处理。

## Security & Privacy Impact

Owner 与 Collaborator 只能查看必要管理状态，不能在 Speaker 撤回、来源未知或删除门禁生效后读取历史原文及派生内容。rights_only Speaker 只能访问本人 Consent、恢复和删除范围，不能获得 Family 浏览权。

ConsentEvent、DeletionLedger、错误日志和处理证据遵守数据最小化：不得保存音频、正文、摘要、Prompt、Embedding、token、验证码或失败响应正文。迟到 Provider / Worker 结果必须重新校验 generation，失效结果不得写入可用正文、索引或发布状态。

## Migration Impact

本 ADR 更新仅归档设计，不创建 Model、Schema、Service、API 或 Alembic revision。后续实现按 SSOT 追加迁移，创建 Consent / Provenance / Restore / Revision / Deletion / Policy / Sanitization 结构，将现有内容接入 Artifact Registry，并统一替换直接硬删入口。

历史 Artifact 只回填确定性来源边并保持 `legacy_unknown`；不回填 active Consent，不创建虚假 Owner Speaker，不把 STT 标签升级为真人身份。隐私事件产生后不得通过 schema downgrade 清除 Ledger 或恢复旧访问。

## Future Boundaries

- 实际音频剪切、上传、对象存储、第三方 STT/LLM 和清理适配器仍需后续实施及能力核验。
- Policy 的生产期限与正式告知文本尚未配置，但其缺值时的 fail-safe 已冻结，不阻塞 C 的结构实现。
- V1 不支持未成年人、不能自主决定者的代理授权，也不开放 User hard delete、身份自动合并或 Owner 转移。
- User Account 删除与法定留存问题继续由 ADR-002 及后续合规评审单独处理，不能从本 ADR 推定。

## Related Documents

- [Part 9.5.5-C Final Implementation Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)
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

| 日期 | 版本 | 变更 |
| --- | --- | --- |
| 2026-10-05 | V1.0 | Part 9.5.5-A；记录 Consent、撤回和删除的已确认约束及 Proposed 实施问题。 |
| 2026-10-05 | V1.1 | Part 9.5.5-C Design Freeze；冻结用途/Source 授权、撤回、恢复、净化、六阶段删除、Ledger、备份恢复与 Policy fail-safe；Implementation Not Started。 |
