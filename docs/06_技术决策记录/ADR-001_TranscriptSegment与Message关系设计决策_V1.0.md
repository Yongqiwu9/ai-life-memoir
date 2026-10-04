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
TranscriptSegment : InterviewMessage = 1 : N
```

即：一个 TranscriptSegment 可以关联多个 InterviewMessage。

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

## Future

如果未来业务要求一个 Segment 必须只产生一个 Message，再增加唯一约束。
