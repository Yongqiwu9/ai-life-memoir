# ADR-001 TranscriptSegment 与 InterviewMessage 关系设计决策 V1.0

## Status

Accepted

## Context

Part 9.5 建立：

```text
Audio
 ↓
Transcript
 ↓
TranscriptSegment
 ↓
InterviewMessage
```

当前数据库：

```text
interview_messages.transcript_segment_id
```

为 nullable foreign key。

## Decision

采用：

```text
TranscriptSegment : InterviewMessage = 0..N
```

即：一个 TranscriptSegment 可以关联零个或多个 InterviewMessage；每个 InterviewMessage 最多关联一个 TranscriptSegment，且该关联可以为空。

数据库不增加：

```text
UNIQUE(transcript_segment_id)
```

## Reason

未来 AI Pipeline 需要支持：

1. STT 原始文本保存
2. 文本清洗
3. Segment 拆分
4. AI Agent 二次生成
5. Memory Extraction

示例：一个 Segment 为“我小时候住在北京，后来去了上海”，可能生成：

```text
Message A: "我小时候住在北京"
Message B: "后来去了上海"
```

## Consequence

优点：

- 支持 AI 后处理
- 支持多阶段消息流
- 不限制未来 Agent

代价：

- 需要通过业务层控制重复引用

## Part 9.5.5-C 补充（设计冻结，未实施）

既有 Segment : Message = 0..N 决策保持不变，不新增 UNIQUE(transcript_segment_id)。

TranscriptSegment.text → InterviewMessage.content 的正文复制必须登记 SourceArtifact / DerivedSource / ArtifactContribution，删除传播覆盖每份正文及其后续衍生物；SET NULL 只断开 FK，不能作为正文清除证明。C 的 Registry、来源门禁及清理合同尚未实现，详细设计见 [Part 9.5.5-C Design Freeze](../../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md) 第 3、7、9、10 部分。

## Future

如果未来业务要求一个 Segment 必须只产生一个 Message，再增加唯一约束。
