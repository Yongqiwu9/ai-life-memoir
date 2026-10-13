# Memory 生成链路设计 V1.0

> 本文为目标链路设计。当前（2026-10-14，HEAD 仍为 `6c12e96e4f83ada7cb7c7dd60fec4283269f8700`）9.6-B 离线 Candidate、不可变 Revision、Owner 精确版本审批及 Memoir 快照已获授权并写入工作区，尚未提交。独立实现复核 PASS WITH FINDINGS；HTTP 15、PG16.15 28 项、Legacy/downgrade 18 个脚本场景在其范围通过；57 项全覆盖未完成。真实 Provider、RAG/Vector、完整生产 Consent/C3/C5/C6 与真实录音转写链路仍未实现。详细 SSOT 见 [9.6-B Contract V1.0](Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)，实际证据边界见 [独立闭环复核](../05_开发阶段记录/Part9.6-B_Validation-Closure_Independent-Review_2026-10-14.md)。下方历史草案状态保留供追溯，以此处最新状态为准。

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

- 目标候选保留来源与提取版本；9.6-B 首版仅单条 user/text Message、离线 Provider，不保存置信度或启用音频/跨消息提取。具体字段以详细草案为准。
- 支持溯源与重放（re-run extraction）。

### 2.4 Memory

- 经 Owner 批准的精确整理版本；认可主观回忆不表示认证客观历史事实。9.6-B 拟采用不可变 Revision＋单一 Proposal 审批；现有人工作品尚未具备此机制。
- 与 FamilyMember 绑定（谁的人生片段），并回链来源 Interview/Message。
- 是后续 Memoir 与 RAG 的可追溯整理来源；仅当前授权/未隔离且有精确批准 proof 的版本可使用，旧审批不绕过撤回/删除。

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


## 7. 9.6-B 已确认范围与实现边界（2026-10-12）

- Owner 显式选一条原始 user/text Message，输出零至多个 Candidate；保存消息或结束 Session 不自动提取。
- 重跑形成新批次与新候选；人工和 AI 编辑均形成不可变 Revision，Owner 明确批准后生效；来源原文不覆盖。
- Candidate 批准只创建新 Memory，已有 Memory 用人工 Revision；新 Memoir 绑定具体已批准 Memory Revision，后续编辑不改变旧章节。
- 旧 Memory / MemoirSection 保留 Legacy，不补造批准/身份/Consent；未知历史来源只可查看必要 metadata。
- 本阶段采用同一 RevisionProposal 的离线业务 FK profile；真实 C3/C4/C6 与 Provider 仍关闭。后续需原地接入 Artifact 与本人用途/删除门禁，不能建立第二审批权威。
- 上方 9.7 Agent / 9.8 Memoir 是历史目标编号；实际推进按路线图 9.6-A 离线 Agent、9.6-B Candidate＋Review、9.6-C 获批后的真实 Provider。RAG/Embedding/写作后台编辑仍属未来范围。

表字段、状态机、权限/API、迁移与57项验收只保存在 [9.6-B详细合同草案](Part9.6-B_Candidate-Revision-Human-Review_Implementation-Contract_V1.0.md)。该草案 **PENDING TARGETED RE-REVIEW / IMPLEMENTATION NOT STARTED / NOT AUTHORIZED**；归档不宣称 AI/STT、真实授权或生产删除能力完成。

## 8. 合同工程修订（2026-10-12）

正式独立审查 PASS WITH FINDINGS；详细合同补齐旧DELETE引用保护与显式回滚、同步Stub timeout分类边界、版本新建例外及不确定提交的只读查询。**42个拟实施源码文件、57项未来验收**；P01–P11与本人授权/删除政策不变。

当前 **REVISED DRAFT — PENDING TARGETED RE-REVIEW**；合同修订不表示代码问题已修复或实际验收通过。详细表/状态/API只保存在合同，不复制到本文。
