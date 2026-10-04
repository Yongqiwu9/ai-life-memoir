# Memory 生成链路设计 V1.0

> 本文为未来设计，当前（Part 9.5）尚未实现 Memory / RAG / Vector DB / AI Agent。

## 1. 目标链路

```text
InterviewMessage
     ↓
AI Extraction
     ↓
Memory Candidate
     ↓
Memory
     ↓
Memoir
```

## 2. 各环节职责

### 2.1 输入：InterviewMessage

- 最小提取单元是一条消息。
- 消息按 `session_id + sequence` 有序，可按角色/来源过滤。
- 通过 `transcript_segment_id` 可回链 `TranscriptSegment → Transcript → AudioRecording`，
  保留“Memory → 原文 → 音频时间点”的证据链。

### 2.2 AI Extraction（Part 9.6）

- 由 AI Service 从消息流中提取人生事实片段：人物、时间、地点、事件、情感。
- 输出为低置信度、待人工确认的 Memory Candidate。
- 不在本环节直接改写最终 Memory，避免把模型幻觉写入权威数据。

### 2.3 Memory Candidate

- 候选记忆：携带来源消息 ID、分段 ID、置信度、提取模型与版本。
- 支持溯源与重放（re-run extraction）。

### 2.4 Memory

- 人工确认/编辑后的权威结构化记忆。
- 与 FamilyMember 绑定（谁的人生片段），并回链来源 Interview/Message。
- 是后续 Memoir 与 RAG 的稳定事实来源。

### 2.5 Memoir（Part 9.8）

- 按时间线/主题从 Memory 组装可编辑回忆录草稿。
- 由 writer-admin 人工修订后定稿。

## 3. RAG 接入

```text
Memory → Embedding → Vector Database（pgvector）
Query → Embedding → 相似检索 → LLM 生成
```

- Embedding 只来自确认后的 Memory（避免把 Candidate/幻觉灌入向量库）。
- Backend 保存 Memory 与引用，AI Service 负责 Embedding 与检索。

## 4. Vector Database 接入

- 首选 PostgreSQL `pgvector`，保持“Backend → Database”单一路径。
- 向量与原文分表存储，Memory 变更时异步更新向量。

## 5. AI Agent 接入（Part 9.7）

```text
InterviewSession(active)
   → Agent 读取消息流 + 用户画像 + 相关 Memory
   → Agent 生成追问/回复
   → InterviewMessage(role=assistant, source=ai_generated)
```

- Agent 输出一律落库为 assistant 消息，保留审计与重放。
- Agent 不得直接写 Memory；只能写消息与 Memory Candidate。

## 6. 边界

- Backend：数据、权限、消息流、Memory 权威存储。
- AI Service：Extraction、Embedding、Agent、Memoir 生成。
- 客户端永远不能伪造 `assistant` / `ai_generated` 消息。
