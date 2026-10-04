# Message 事件模型设计 V1.0

## 1. 模型

```text
InterviewSession 1 ─── N InterviewMessage
InterviewMessage 0..N ── TranscriptSegment（transcript_segment_id）
```

| 字段 | 说明 |
| --- | --- |
| role | user / assistant / system |
| source | text / audio_transcript / ai_generated / system |
| content | 文本内容 |
| sequence | Session 内有序 |
| transcript_segment_id | 可空，回链音频分段 |

`role` 回答“谁在说”，`source` 回答“内容从哪来”。

## 2. 消息来源

| source | role | 产生者 |
| --- | --- | --- |
| text | user | 用户直接输入文字 |
| audio_transcript | user | 用户语音经 STT 转写 |
| ai_generated | assistant | AI 生成回复/追问 |
| system | system | 系统/流程消息（预留，客户端不可创建） |

## 3. 三种来源的进入路径

### 用户输入（text）

```text
POST /api/v1/sessions/{session_id}/messages
{ "role": "user", "source": "text", "content": "..." }
```

客户端只允许 `role=user, source=text`。

### STT 生成（audio_transcript）

由服务端 Pipeline 调用：

```text
TranscriptSegment → create_transcript_message
→ InterviewMessage(role=user, source=audio_transcript, transcript_segment_id)
```

客户端不能直接创建 audio_transcript 消息。

### AI 生成（ai_generated）

未来 AI Agent（Part 9.7）由服务端写入：

```text
InterviewMessage(role=assistant, source=ai_generated)
```

当前不实现 AI 消息生成逻辑，仅保留模型与语义边界。

## 4. Message 与 TranscriptSegment 的关系

```text
TranscriptSegment（0..N）── InterviewMessage.transcript_segment_id
```

- 不是所有 Message 都有 Segment：text 消息与 ai_generated 消息没有。
- audio_transcript 消息必须回链 Segment，从而支持：

```text
消息文字 → TranscriptSegment → Transcript → AudioRecording
→ 跳转 start_ms/end_ms 播放原音
```

- 该外键为 `SET NULL`：删除 Segment 不会删除 Message，仅断开回链。

## 5. Message来源关系

```less
Text Input

User
 |
 |
InterviewMessage
(source=text)


Audio STT

Audio
 |
STT
 |
TranscriptSegment
 |
InterviewMessage
(source=audio_transcript)


AI

AI Agent
 |
InterviewMessage
(source=ai_generated)
```

明确：

```text
TranscriptSegment != Message
```

Segment 是语音识别结果，Message 是系统事件。
