# Interview 生命周期状态机设计 V1.0

> 本文为目标设计基线。当前代码（Part 9.4）使用 `draft/in_progress/completed/cancelled`，
> 本设计将其收敛为 `draft/active/completed/archived`，落地时需要一次性迁移，
> 详见文末“与当前实现的差异”。

## 1. Interview 状态

```text
draft → active → completed → archived
  │                 │
  └── cancelled ────┘（取消路径）
```

| 状态 | 含义 |
| --- | --- |
| draft | 已创建，未开始访谈 |
| active | 正在访谈 |
| completed | 访谈完成 |
| archived | 已归档（从工作区隐藏） |
| cancelled | 取消（终态） |

### 转换条件

- `draft → active`：用户开始访谈（创建/激活第一个 Session）
- `active → completed`：用户或系统确认访谈完成
- `completed → archived`：用户归档
- `draft/active → cancelled`：用户取消
- `archived` 与 `cancelled` 为终态（不允许回到 active）

## 2. Session 状态

```text
created → recording → processing → completed
                    └───────────┐
                                └→ cancelled
```

| 状态 | 含义 |
| --- | --- |
| created | 会话已创建 |
| recording | 正在录音 |
| processing | 音频上传/STT/处理中 |
| completed | 处理完成 |
| cancelled | 取消（终态） |

### 转换条件

- `created → recording`：开始录音（产生 AudioRecording）
- `recording → processing`：录音结束，进入音频处理队列
- `processing → completed`：Transcript 完成并回写 Message
- 任意非终态 `→ cancelled`：用户或系统取消

## 3. 时间字段写入规则

| 字段 | 写入时机 |
| --- | --- |
| Interview.started_at | draft → active 时写入 |
| Interview.completed_at | active → completed 时写入 |
| Session.started_at | created → recording 时写入 |
| Session.ended_at | recording 结束（进入 processing）时写入 |
| AudioRecording.started_at / ended_at | 上传/处理开始与结束时写入 |
| created_at / updated_at | 由系统统一维护 |

所有时间字段一律 timezone-aware UTC。

## 4. 未来 AI 流程入口

```text
Session(processing)
   ↓
AudioRecording(completed)
   ↓
Transcript(completed)
   ↓
TranscriptSegment → InterviewMessage(source=audio_transcript)
   ↓
AI Extraction（Part 9.6 起）
```

AI Agent（Part 9.7）可在 `active` 会话中读取消息流并生成 assistant 消息；
Memoir（Part 9.8）消费 `completed` Interview 的 Memory。

## 5. 与当前实现的差异

- 当前 Interview 状态：`draft/in_progress/completed/cancelled`；本设计改为 `draft/active/completed/archived`。
- 当前 Session 状态：`active/completed/cancelled`；本设计改为 `created/recording/processing/completed`。
- 当前 `started_at/completed_at/ended_at` 为 nullable 占位，尚未有任何流程写入。

落地建议：在进入 Part 9.6 前统一状态枚举、数据迁移与状态转换校验，避免 AI Pipeline 建立在旧状态机上。
