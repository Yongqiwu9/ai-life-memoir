# ADR-009 AI-STT 第三方数据处理边界

## Status

Proposed

架构约束与已确认本人授权原则记录在 Decision Constraints。Provider 选择、数据处理政策及具体集成协议尚未冻结。

## Context

未来录音转写和 Memory Extraction 可能将音频、对话或其他必要上下文发送给第三方服务。内容会包含讲述者与其谈及人物的个人信息和情感表达；家庭可访问不能直接推定外部处理已获授权。

项目规定 Backend 负责业务数据和权限，AI Service 独立负责 AI 处理。Provider 的处理能力与对数据的保存、训练使用、地域和删除能力，需要在实际接入前明确。

## Current Implementation

- Backend 已有 AudioRecording、Transcript、TranscriptSegment 的元数据模型/API，未实现音频二进制上传、Object Storage 或真实 STT 调用。
- `AudioRecording.storage_key` 是可空占位字段；当前创建元数据不生成实际音频存储对象。
- `Transcript.provider/model/language` 为可空元数据；客户端可提交这些值及 `status`，CRUD 仅保存记录。它们不能证明已调用某厂商、某模型或完成转写，也不代表最终 Provider 选择。
- `create_transcript_message` 是服务端写消息辅助函数，尚无 Provider → STT → Transcript → Message 的完整处理作业。
- `services/ai-service/` 为占位目录，没有实际服务；MemoryCandidate、Memory、AI Pipeline 和第三方删除传播尚未实现。
- 现有访问检查沿 Family Owner 链进行；没有讲述者 Consent、Family 协作权限或外部处理授权审计。

## Proposed Decision

### Target Design

```text
Client
  ↓
Backend
  ↓
AI Service
  ↓
LLM / STT Provider
```

业务数据仍遵守 `Client → Backend API → Database`。Backend 校验用户/Family 访问权限、相应用途的讲述者授权及业务状态，向 AI Service 发起允许的处理；AI Service 调用 Provider。结果返回受控业务入口，由 Backend Service 校验并通过 CRUD 写入数据库。

客户端不得直接调用 LLM / STT Provider，Provider 不得直接写 Backend Database。未来 Provider 如需异步回调，其接收方、身份验证、任务关联和结果校验协议仍待设计；回调不构成直连数据库或绕过 Backend 权限的理由。

在选择 Provider 和集成方案前，列明实际发送内容、用途、处理结果、可见的元数据及删除传播能力。需要产品和架构负责人明确保存、训练使用、地域、加密、日志/脱敏和备份规则；本轮只记录边界及问题，不指定厂商或固定政策。

## Decision Constraints

- 项目既定架构为 Client → Backend → AI Service → LLM / STT Provider；客户端不得直连数据库或 AI Provider，Provider 不得直写 Backend Database。
- Backend 负责业务数据、权限及事务；AI Service 负责提取/生成等 AI 能力。权限判断不能交给 Provider，也不能信任客户端提交的 `user_id` 或处理完成状态。
- 实际讲述者需要同意录音、转写、AI 分析与 Family 共享。Owner 不能代替具有自主决定能力的成年讲述者同意。
- 有效撤回后，未来针对本人内容的相应处理和共享必须停止。有效本人删除请求不能被 Owner 否决；正常产品路径需要立即移除已删除内容。
- 外部留存、训练使用、地域、加密方案、日志政策、删除传播和备份最终清除周期均未确定。本轮不得把 OpenAI、DeepSeek 或其他 Provider 作为最终产品选择。
- Part 9.5 只完成 Audio/STT 数据模型/API 范围，不代表上传、存储、STT Provider 或 AI Pipeline 已完成。

## Consequences

### Positive

- 保持权限与业务写入集中在 Backend，来源及处理任务可追踪。
- Provider 可在明确产品处理政策后选型，不把元数据字段误解为厂商绑定。
- 为撤回、删除、重试和第三方结果验证留下统一业务入口。

### Negative / Trade-offs

- 需要实现 Backend、AI Service 与 Provider 之间的任务、结果和认证协议。
- 第三方保存与删除能力可能限制 Provider 选择，必须在实际传输个人内容前解决。
- 本人撤回/删除会跨越队列、正在执行的任务、业务存储与第三方副本，普通数据库级联不足以覆盖。

## Security & Privacy Impact

现有禁止在日志中输出密码、token、API key 的规则继续适用，Provider 凭据必须由服务端环境变量或 Secret Manager 管理。讲述原文、音频、提示词和 Provider 响应是否允许记录、如何脱敏、谁能访问及保存多久，尚需明确，不能从现有日志规则推定。

未来传输前需要定义必要内容范围并检查用途授权。Provider 响应须由服务端验证与任务对应关系，不能视为权限凭证、真人同意或已经人工确认的 Memory。撤回后的迟到结果及 Provider 端副本需要有明确处理规则。

## Migration Impact

本轮没有选择 Provider、修改配置、实现 AI Service、添加第三方 SDK 或创建数据库迁移。当前 `Transcript.provider/model` 元数据保持原状。

未来可能需要记录处理任务、Provider 请求与删除传播证据，以及与来源和 Consent 的关联；具体结构取决于选定协议与政策，需另行设计并通过 Alembic 落地，不在本轮冻结。

## Open Questions

- 首版 LLM / STT Provider 如何选择，采用托管服务还是其他部署方式，能力与数据处理条件如何验收？
- 需要向 Provider 发送哪些音频、原文、人物信息和上下文；是否脱敏、如何在不改变讲述原意的情况下最小化内容？
- Provider 是否保存输入/输出和请求日志，保留多久；是否用于训练或改进产品，如何验证对应账户和接口的实际设置？
- 处理区域、跨区域副本、访问主体和部署地域由谁确认，有哪些产品要求？
- 传输与存储加密、密钥管理、服务间认证和异步回调验证采用什么方案？
- Backend / AI Service / Provider 的日志与错误报告允许含哪些内容，如何脱敏，权限与保留期是什么？
- Consent 是否需要就外部处理方式补充说明或重新取得本人同意，授权范围如何关联任务？
- 撤回时如何取消队列或运行中的调用，Provider 已接收内容和迟到结果如何处理？
- 本人或 Owner 的有效删除如何传播至 Provider 及其他副本，如何取得删除证据，失败或不支持删除时如何处理？
- Object Storage、业务存储及第三方备份最终清除周期如何确定？不得在本轮推定固定天数。

## Related Documents

- [Root AGENTS](../../../AGENTS.md)
- [Backend AGENTS](../../../apps/backend/AGENTS.md)
- [系统架构总览](../../01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型基线](../../02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [Memory 生成链路](../../04_AI设计/Memory生成链路设计_V1.0.md)
- [ADR-006 Consent 授权撤回与删除策略](<ADR-006 Consent授权撤回与删除策略.md>)
- [ADR-008 MemoryCandidate 确认流程](<ADR-008 MemoryCandidate确认流程.md>)

## Related Code

- [AudioRecording Model](../../../apps/backend/app/models/audio_recording.py)
- [Transcript Model](../../../apps/backend/app/models/transcript.py)
- [Transcript Schema](../../../apps/backend/app/schemas/transcript.py)
- [Audio Service](../../../apps/backend/app/services/audio_recording.py)
- [Transcript Service](../../../apps/backend/app/services/transcript.py)
- [Transcript CRUD](../../../apps/backend/app/crud/transcript.py)
- [Audios API](../../../apps/backend/app/api/v1/audios.py)
- [Message Service](../../../apps/backend/app/services/interview_message.py)
- [AI Service 目录（当前占位）](../../../services/ai-service/)

## Revision History

| 日期 | 修订 |
| --- | --- |
| 2026-10-05 | Part 9.5.5-A：记录第三方处理架构与授权边界；Provider 和具体数据处理政策保持 Proposed，未接入实际服务。 |
