# Part 9.5 — Audio/STT 数据模型设计基线 V1.0

## 1. 关系总览

```text
InterviewSession 1 ─── N AudioRecording
AudioRecording   1 ─── N Transcript
Transcript       1 ─── N TranscriptSegment
TranscriptSegment 0..N ── InterviewMessage.transcript_segment_id
```

> Segment 与 Message 为 0..N 关系，具体约束由业务层控制（不增加数据库 UNIQUE 约束）。

核心链路：

```text
Audio → STT → Transcript → TranscriptSegment → InterviewMessage
```

## 2. AudioRecording

音频的**元数据**实体，音频二进制保存在未来 Object Storage 中。

| 字段 | 说明 |
| --- | --- |
| id | UUID 主键 |
| session_id | FK → interview_sessions.id（CASCADE） |
| storage_key | Object Storage 对象键。当前为 nullable 占位字段，未来接入上传服务后由服务端生成 |
| original_filename / mime_type / size_bytes / duration_ms | 音频元数据 |
| status | pending / processing / completed / failed |
| started_at / ended_at | 处理生命周期时间 |
| created_at / updated_at | timezone-aware UTC |

Owner Isolation 链：

```text
AudioRecording → InterviewSession → Interview → FamilyMember → Family → User
```

## 3. Transcript

一次 STT 尝试的结果记录。**Audio 与 Transcript 是 1:N**，同一个音频可以多次、多 Provider、多模型重试。

| 字段 | 说明 |
| --- | --- |
| id | UUID 主键 |
| audio_recording_id | FK → audio_recordings.id（CASCADE） |
| provider / model / language | STT 厂商抽象，不绑定具体厂商 |
| status | pending / processing / completed / failed |
| text | STT Pipeline 完成后写入。当前仅作为数据字段预留 |
| duration_ms | 音频时长 |

本 Part 不真正接入外部 STT Provider，只建立数据模型与处理抽象。

## 4. TranscriptSegment

转写的**时间对齐分段**，是“从文字跳回音频时间点”的核心数据。

| 字段 | 说明 |
| --- | --- |
| id | UUID 主键 |
| transcript_id | FK → transcripts.id（CASCADE） |
| sequence | Transcript 内有序 |
| speaker | 说话人（未来 Speaker Identification） |
| text | 分段文本 |
| start_ms / end_ms | 音频时间定位 |
| confidence | STT 置信度 |

### Segment 存在意义

未来必须支持：

```text
用户看到一句文字
→ 定位 TranscriptSegment
→ 定位 Transcript → AudioRecording
→ 跳转到 start_ms / end_ms 播放原始音频
```

因此 Segment 不能简化为纯文本表，必须保留时间定位能力。

## 5. InterviewMessage

会话中的一条消息（Part 9.4 已有，Part 9.5 最小扩展）。

- `role`：user / assistant / system
- `source`：text / audio_transcript / ai_generated / system
- `transcript_segment_id`：可空 FK → transcript_segments.id（SET NULL）

`role` 与 `source` 分离：`role` 表示发言角色，`source` 表示内容来源。

## 6. 为什么 Message 不是 Audio

- AudioRecording 是**媒体资产**（二进制 + 元数据），属于 Session 的采集侧。
- InterviewMessage 是**对话内容**，属于会话逻辑侧。
- 两者生命周期不同：音频要经过上传、转写、处理；消息要参与后续 Memory 提取。
- 将音频二进制/元数据塞进消息会破坏“DB 只存元数据、Object Storage 存二进制”的边界。

## 7. STT 如何进入 Message

```text
AudioRecording
   ↓ STT
Transcript
   ↓ 分段
TranscriptSegment
   ↓ 服务端 create_transcript_message
InterviewMessage(role=user, source=audio_transcript, transcript_segment_id=segment.id)
```

- 该路径只允许服务端（未来 AI/STT Pipeline）调用。
- 普通客户端创建消息只能 `role=user, source=text`，不能伪造 assistant/ai_generated/system。

## 8. 后续 Memory 如何引用

Memory 提取的最小输入单位是 `InterviewMessage`，并可通过 `transcript_segment_id` 回链到：

```text
TranscriptSegment → Transcript → AudioRecording
```

从而保留“Memory → 原文 → 音频时间点”的证据链，支持溯源、跳转与 Fact Check。
