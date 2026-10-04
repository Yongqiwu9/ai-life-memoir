# AI人生回忆录平台

# Part 9.5 DeepSeek Pro 实施任务书 V1.0

## Audio / STT 数据基础设施实施

**任务级别：高强度后端实施任务**\
**执行模型：DeepSeek Pro / 高强度代码模式**\
**执行阶段：Part 9.5**\
**前置基线：Part 9.4 已封板，Part 9.5 过渡设计已完成**\
**本任务性质：正式代码实施任务**

------------------------------------------------------------------------

# 一、执行前必须阅读的资料

开始任何代码修改前，必须依次阅读：

``` text
1. 根目录 AGENTS.md

2. apps/backend/AGENTS.md

3. Part 9.5 过渡设计基线：
   AI人生回忆录平台_Part9.5_过渡设计基线_V1.0.md

4. 当前 Part 9.4 Interview 实现：
   apps/backend/app/models/interview.py
   apps/backend/app/models/interview_session.py
   apps/backend/app/models/interview_message.py
   apps/backend/app/models/family_member.py

5. 当前 Part 9.4：
   schemas/
   crud/
   services/
   api/v1/
   tests/
   alembic/versions/

6. templates/ 中与 FastAPI / SQLAlchemy / CRUD / 文件处理相关的模板
```

如果实际仓库中的代码与设计文档存在冲突：

> **不得自行修改设计基线。**

必须先识别冲突，并在最终报告中明确：

``` text
设计基线：
当前代码：
冲突点：
建议：
```

只有明确属于实现层细节、且不改变设计语义的内容，才允许自行决定。

------------------------------------------------------------------------

# 二、任务目标

正式实施：

> **Part 9.5 --- Audio / STT 数据基础设施**

核心链路：

``` text
Interview
    ↓
InterviewSession
    ↓
AudioRecording
    ↓
STT
    ↓
Transcript
    ↓
TranscriptSegment
    ↓
InterviewMessage
    ↓
Memory Extraction
```

本 Part 只负责：

``` text
AudioRecording
Transcript
TranscriptSegment
以及必要的 Audio/STT 数据处理基础设施
```

不实现：

``` text
Memory
Embedding
RAG
Memoir
LLM
LangGraph
AI Interview Agent
自动人生故事提取
```

------------------------------------------------------------------------

# 三、最高优先级架构原则

## 3.1 Audio 必须属于 Session

关系：

``` text
InterviewSession 1 ─── N AudioRecording
```

禁止：

``` text
User → Audio
Family → Audio
FamilyMember → Audio
Interview → Audio
```

作为 Audio 的直接业务归属关系。

Audio 必须通过：

``` text
AudioRecording
→ InterviewSession
→ Interview
→ FamilyMember
→ Family
→ User
```

完成 Owner Isolation。

------------------------------------------------------------------------

# 四、AudioRecording Model

新增：

``` text
apps/backend/app/models/audio_recording.py
```

建议字段：

``` text
id
session_id
storage_key
original_filename
mime_type
size_bytes
duration_ms
status
started_at
ended_at
created_at
updated_at
```

要求：

-   UUID PK
-   `session_id` FK → `interview_sessions.id`
-   时间字段 timezone-aware
-   必要索引
-   与现有 SQLAlchemy 2.x 风格保持一致
-   与现有 Model timestamp 约定一致

Audio 与 Session 为包含关系：

``` text
Session
  ↓ CASCADE
AudioRecording
```

不得擅自扩大级联范围。

------------------------------------------------------------------------

# 五、Audio 存储边界

必须严格遵守：

``` text
PostgreSQL
=
Audio Metadata

Object Storage
=
Audio Binary
```

数据库不得保存：

``` text
BYTEA
Large Binary
Base64 Audio
```

等大型音频内容。

`storage_key` 只保存对象存储中的对象键。

例如：

``` text
audio/{session_id}/{audio_id}.wav
```

具体 key 格式可以根据现有项目约定实现，但必须：

-   可唯一定位
-   不包含用户真实隐私信息
-   不依赖本地 Windows 路径
-   不保存完整公网 URL 作为数据库主存储字段

------------------------------------------------------------------------

# 六、Audio 状态

V1 状态：

``` text
pending
processing
completed
failed
```

必须明确：

``` text
AudioRecording.status
```

表示 Audio / STT 处理状态。

它不是：

``` text
Interview.status
Session.status
```

不能混用。

------------------------------------------------------------------------

# 七、Transcript Model

新增：

``` text
apps/backend/app/models/transcript.py
```

建议字段：

``` text
id
audio_recording_id
provider
model
language
status
text
duration_ms
created_at
updated_at
```

关系：

``` text
AudioRecording 1 ─── N Transcript
```

不要强制 1:1。

原因：

同一个 Audio 可以：

``` text
第一次 STT
↓
失败

第二次 STT
↓
重新处理

第三次 STT
↓
换模型重新处理
```

所以必须允许多个 Transcript 记录。

------------------------------------------------------------------------

# 八、Transcript 状态

V1 至少支持：

``` text
pending
processing
completed
failed
```

必须能够表达：

``` text
等待处理
处理中
成功
失败
```

如果实现中需要额外状态，必须先确认不会改变设计语义，并在最终报告中说明。

不得无理由增加复杂状态机。

------------------------------------------------------------------------

# 九、Transcript Provider 抽象

Transcript 必须记录：

``` text
provider
model
language
```

目的是让上层业务不依赖某个具体 STT 厂商。

允许未来支持：

``` text
Whisper
Deepgram
Google STT
Azure Speech
本地 STT
其他 Provider
```

本 Part：

> **不要真正接入外部 STT Provider。**

只建立数据模型和必要的处理抽象。

不得：

-   调用真实付费 STT API
-   把 API Key 写入代码
-   新增真实 Provider Secret
-   创建假的外部 STT 成功结果作为生产逻辑

------------------------------------------------------------------------

# 十、TranscriptSegment Model

新增：

``` text
apps/backend/app/models/transcript_segment.py
```

建议字段：

``` text
id
transcript_id
sequence
speaker
text
start_ms
end_ms
confidence
created_at
```

关系：

``` text
Transcript 1 ─── N TranscriptSegment
```

要求：

-   UUID PK
-   `transcript_id` FK
-   sequence 在 Transcript 内有序
-   `start_ms` / `end_ms` 用于音频时间定位
-   speaker 支持未来 Speaker Identification
-   confidence 支持 STT 置信度
-   必要索引

------------------------------------------------------------------------

# 十一、TranscriptSegment 的核心价值

必须保证未来能够实现：

``` text
用户看到一句文字
        ↓
定位 TranscriptSegment
        ↓
定位 Transcript
        ↓
定位 AudioRecording
        ↓
定位原始音频
        ↓
跳转到 start_ms / end_ms
```

因此不能把 Segment 简化成单纯文本表。

------------------------------------------------------------------------

# 十二、InterviewMessage 的最小扩展

Part 9.4 已有：

``` text
InterviewMessage
```

Part 9.5 可以进行**最小必要修改**。

设计要求：

``` text
role
```

和：

``` text
source
```

必须分离。

建议 source：

``` text
text
audio_transcript
ai_generated
system
```

例如：

``` text
role = user
source = text
```

表示用户直接输入文字。

``` text
role = user
source = audio_transcript
```

表示用户语音经过 STT。

``` text
role = assistant
source = ai_generated
```

表示 AI 生成。

------------------------------------------------------------------------

# 十三、transcript_segment_id

如果当前设计和数据库实现允许，InterviewMessage 应能够关联：

``` text
transcript_segment_id
```

关系：

``` text
TranscriptSegment
      │
      │ 0..1
      ▼
InterviewMessage
```

注意：

不是所有 Message 都有 TranscriptSegment。

例如：

``` text
User Text
→ 无 TranscriptSegment

User Audio
→ 有 TranscriptSegment

AI Assistant
→ 无 TranscriptSegment
```

不得强制所有 Message 必须关联 Segment。

------------------------------------------------------------------------

# 十四、Message Role 安全边界

继续保持 Part 9.4 的安全原则：

客户端创建 Message 时：

``` text
role = user
```

客户端不得创建：

``` text
assistant
system
```

Audio/STT 产生的 Message：

``` text
role = user
source = audio_transcript
```

AI Assistant Message：

``` text
role = assistant
source = ai_generated
```

本 Part 不实现 AI Assistant Message 生成逻辑。

------------------------------------------------------------------------

# 十五、STT → Message 的职责边界

正确架构：

``` text
AudioRecording
      ↓
STT
      ↓
Transcript
      ↓
TranscriptSegment
      ↓
InterviewMessage
```

但是本 Part 不实现完整 AI Pipeline。

可以提供：

``` text
Service
CRUD
数据转换辅助逻辑
```

但不得把以下内容混入：

``` text
LLM
AI Agent
Memory Extraction
RAG
Memoir
```

------------------------------------------------------------------------

# 十六、API 设计

Part 9.5 应提供最小可用 API，用于：

``` text
创建 Audio metadata
查询 Audio
查询 Audio 下 Transcript
查询 Transcript 下 Segment
```

具体 URL 必须遵循当前项目：

``` text
/api/v1
```

并遵循已有资源的命名风格。

推荐结构：

``` text
POST /api/v1/sessions/{session_id}/audios
GET  /api/v1/sessions/{session_id}/audios
GET  /api/v1/audios/{audio_id}

POST /api/v1/audios/{audio_id}/transcripts
GET  /api/v1/audios/{audio_id}/transcripts
GET  /api/v1/transcripts/{transcript_id}

GET /api/v1/transcripts/{transcript_id}/segments
```

如果当前项目已有统一的 REST 路径风格，应优先遵循现有风格。

不要因为个人偏好大规模重命名 Part 9.4 API。

------------------------------------------------------------------------

# 十七、Audio API 的 Security

任何 Audio API 都必须经过：

``` text
get_current_user
```

并完成：

``` text
current_user
 ↓
Family
 ↓
FamilyMember
 ↓
Interview
 ↓
Session
 ↓
Audio
```

才能访问。

禁止：

``` text
db.get(AudioRecording, audio_id)
→ 直接返回
```

这种绕过 ownership 的路径。

------------------------------------------------------------------------

# 十八、Transcript API 的 Security

Transcript：

``` text
Transcript
 ↓
Audio
 ↓
Session
 ↓
Interview
 ↓
FamilyMember
 ↓
Family
 ↓
current_user
```

必须完整验证。

不能因为知道：

``` text
transcript_id
```

就直接读取。

------------------------------------------------------------------------

# 十九、TranscriptSegment API 的 Security

同样：

``` text
TranscriptSegment
 ↓
Transcript
 ↓
Audio
 ↓
Session
 ↓
Interview
 ↓
FamilyMember
 ↓
Family
 ↓
current_user
```

必须完整验证。

跨用户访问：

``` text
404
```

不得返回：

``` text
403
```

以避免泄露资源存在性。

------------------------------------------------------------------------

# 二十、Schema 安全

Create / Update Schema 不允许客户端控制：

``` text
user_id
owner_id
family_id
family_member_id
interview_id
session_id
audio_recording_id
transcript_id
```

这些关系必须从：

``` text
URL path
+
数据库关系
```

确定。

------------------------------------------------------------------------

# 二十一、Storage API 边界

如果本 Part 只实现 metadata：

允许：

``` text
POST audio metadata
```

但不得假装：

``` text
文件已经上传
```

除非项目已经有真正 Object Storage 集成。

如果当前项目没有 Object Storage：

> 不要为了 Part 9.5 擅自引入完整 S3/MinIO 云存储系统。

可以保留：

``` text
storage_key
```

作为数据模型字段，并在实现报告中明确：

``` text
Object Storage integration = future work
```

------------------------------------------------------------------------

# 二十二、CRUD / Service 分层

继续严格遵守：

``` text
Router
 ↓
Service
 ↓
CRUD
 ↓
Model
```

Router：

只负责：

-   HTTP
-   dependency
-   path params
-   schema
-   response

CRUD：

只负责：

-   数据库查询
-   数据库写入

CRUD 不负责：

``` text
JWT
HTTPException
Owner Isolation
业务状态判断
```

Service：

负责：

-   Owner Isolation
-   业务规则
-   资源关系
-   状态检查
-   数据转换

------------------------------------------------------------------------

# 二十三、建议文件结构

最终预计：

``` text
apps/backend/app/
├── models/
│   ├── audio_recording.py
│   ├── transcript.py
│   └── transcript_segment.py
│
├── schemas/
│   ├── audio_recording.py
│   ├── transcript.py
│   └── transcript_segment.py
│
├── crud/
│   ├── audio_recording.py
│   ├── transcript.py
│   └── transcript_segment.py
│
├── services/
│   ├── audio_recording.py
│   ├── transcript.py
│   └── transcript_segment.py
│
└── api/v1/
    └── audios.py
```

如果当前项目的命名结构需要拆成多个 Router，可以遵循现有风格。

------------------------------------------------------------------------

# 二十四、Alembic Migration

必须创建新的 Alembic revision。

当前 Part 9.4 head：

``` text
6ca666161c77
```

Part 9.5 migration 必须：

``` text
down_revision = 6ca666161c77
```

最终必须：

``` text
6ca666161c77
      ↓
Part 9.5 revision
```

保持单一 head。

必须验证：

``` text
alembic upgrade head
alembic current
alembic heads
alembic check
```

------------------------------------------------------------------------

# 二十五、数据库关系

最终必须形成：

``` text
interview_sessions
        │
        │ 1:N
        ▼
audio_recordings
        │
        │ 1:N
        ▼
transcripts
        │
        │ 1:N
        ▼
transcript_segments
```

以及：

``` text
transcript_segments
        │
        │ 0..1
        ▼
interview_messages
```

如果 Message 外键关系在实现阶段发现会造成不合理的级联或循环依赖：

> 不得擅自解决成另一套架构。

必须报告冲突。

------------------------------------------------------------------------

# 二十六、级联删除

建议严格保持包含关系：

``` text
Session
 ↓ CASCADE
AudioRecording
 ↓ CASCADE
Transcript
 ↓ CASCADE
TranscriptSegment
```

但：

``` text
User
 ↓
Family
 ↓
Member
 ↓
Interview
 ↓
Session
 ↓
Audio
```

这一整条 User 删除策略仍属于未来产品决策。

不得因为本 Part 自动新增 User Delete API。

不得修改 Part 9.3 的：

``` text
families.owner_id ondelete
```

除非发现当前设计基线无法实施；如发生冲突必须先报告。

------------------------------------------------------------------------

# 二十七、Tests 必须覆盖

至少新增：

## Audio

1.  创建 Audio
2.  获取 Audio
3.  Audio 列表
4.  Audio 不属于其他 User
5.  跨 Family Audio 返回 404
6.  非法 Session ID 返回 404
7.  Audio metadata schema 校验

## Transcript

8.  创建 Transcript
9.  获取 Transcript
10. Transcript 列表
11. 跨用户 Transcript 返回 404
12. 非法 Audio ID 返回 404
13. failed Transcript 可以保存

## TranscriptSegment

14. 创建 Segment
15. 获取 Segment
16. Segment 列表按 sequence 排序
17. 跨用户 Segment 返回 404
18. 非法 Transcript ID 返回 404
19. start_ms / end_ms 校验

## Message integration

20. Audio Transcript Segment 可以关联 User Message
21. User audio message 的： `role = user` `source = audio_transcript`
22. AI assistant 不允许由普通客户端创建
23. Text message 不要求 transcript_segment_id

## Isolation

必须至少覆盖：

``` text
User A
 ├── Family A
 │    └── Member A
 │         └── Interview A
 │              └── Session A
 │                   └── Audio A
 │
User B
 └── Family B
      └── Member B
           └── Interview B
                └── Session B
                     └── Audio B
```

验证：

``` text
A 不能读取 B Audio
A 不能读取 B Transcript
A 不能读取 B Segment
B 不能读取 A Audio
```

------------------------------------------------------------------------

# 二十八、Migration Tests

必须验证：

``` text
alembic upgrade head
```

成功。

并检查：

``` text
current == head
```

同时：

``` text
alembic check
```

必须：

``` text
No new upgrade operations detected.
```

------------------------------------------------------------------------

# 二十九、真实 PostgreSQL 验证

必须使用当前开发 PostgreSQL。

不要只用 SQLite。

至少验证：

``` text
CREATE
READ
ownership isolation
FK
CASCADE
transaction
```

测试完成后：

``` text
清理测试数据
```

不得留下大量垃圾测试数据。

------------------------------------------------------------------------

# 三十、不要修改的范围

本任务明确禁止修改：

``` text
apps/elder-app/
apps/writer-admin/
services/ai-service/
templates/
packages/
infra/
database/
```

除非：

> 明确属于 Backend Part 9.5 必须修改的共享接口，而且设计基线明确要求。

默认全部禁止。

------------------------------------------------------------------------

# 三十一、不要实施的功能

严禁在本 Part 顺手实现：

``` text
❌ Memory
❌ MemoryEmbedding
❌ RAG
❌ Memoir
❌ LLM
❌ LangGraph
❌ AI Agent
❌ Interview AI 自动追问
❌ 自动人生故事提取
❌ Fact Checker
❌ Vector Database
❌ 支付
❌ Subscription
❌ User Delete
```

尤其禁止：

> "为了未来方便"提前创建大量表。

本 Part 只做 Audio/STT 基础设施。

------------------------------------------------------------------------

# 三十二、不要擅自修复 Part 9.4 技术债

除非本 Part 无法实现，否则不要修改：

``` text
Message sequence 并发问题
User → Family CASCADE
Session / Message 分页
Owner 查询性能优化
Enum DB CHECK
Interview 完整状态机
```

如果发现 Audio/STT 实施确实依赖其中某项：

必须先判断：

``` text
是否真正阻塞？
```

如果不是：

> 记录 Technical Debt，不修改。

------------------------------------------------------------------------

# 三十三、模板使用规则

必须：

``` text
先找 templates/
↓
判断是否存在可复用模板
↓
参考模板
↓
参考当前项目相似实现
↓
最小修改
```

禁止：

``` text
复制模板后整项目重构
```

Templates：

> 只作为代码生产参考，不得 runtime import。

------------------------------------------------------------------------

# 三十四、代码质量要求

必须：

``` text
Python 3.12+
FastAPI
SQLAlchemy 2.x
Pydantic v2
Alembic
Ruff
Pytest
```

遵守：

``` text
timezone-aware datetime
UUID
typed SQLAlchemy mappings
```

不要引入没有必要的新框架。

------------------------------------------------------------------------

# 三十五、执行顺序

严格按照以下顺序：

``` text
Step 1
读取 AGENTS.md

↓

Step 2
读取 Part 9.5 Design Baseline

↓

Step 3
检查当前 Part 9.4 实现

↓

Step 4
检查 templates

↓

Step 5
设计最终文件变更清单

↓

Step 6
实现 Models

↓

Step 7
实现 Schemas

↓

Step 8
实现 CRUD

↓

Step 9
实现 Services

↓

Step 10
实现 Router

↓

Step 11
最小扩展 InterviewMessage

↓

Step 12
更新 models_import.py

↓

Step 13
更新 main.py

↓

Step 14
创建 Alembic Migration

↓

Step 15
创建 Tests

↓

Step 16
运行 pytest

↓

Step 17
运行 ruff

↓

Step 18
运行 alembic

↓

Step 19
运行 PostgreSQL smoke test

↓

Step 20
检查 git diff

↓

Step 21
检查 git status

↓

Step 22
最终报告
```

------------------------------------------------------------------------

# 三十六、Git 要求

Part 9.5 完成后创建独立 commit。

建议：

``` text
feat: implement audio and stt data infrastructure
```

不要：

``` text
git reset --hard
git rebase
git amend previous Part 9.4 commit
```

不要修改：

``` text
79bb296
```

Part 9.4 必须保持历史完整。

------------------------------------------------------------------------

# 三十七、提交前安全检查

必须确认：

``` text
.env
```

没有进入 Git。

不得出现：

``` text
API_KEY
SECRET_KEY
PASSWORD
TOKEN
```

等真实 secret。

如果测试需要密码：

> 使用测试 fixture，不使用真实密码。

------------------------------------------------------------------------

# 三十八、最终验收命令

至少运行：

``` powershell
pytest
```

``` powershell
ruff check .
```

``` powershell
ruff format --check .
```

``` powershell
alembic upgrade head
```

``` powershell
alembic current
```

``` powershell
alembic heads
```

``` powershell
alembic check
```

并执行真实 PostgreSQL smoke test。

------------------------------------------------------------------------

# 三十九、最终报告必须包含

DeepSeek 完成后必须严格按以下结构报告：

## 1. Status

``` text
PASS / PASS WITH FINDINGS / BLOCKED
```

## 2. Files Added

完整列出新增文件。

## 3. Files Modified

完整列出修改文件。

## 4. Database

说明：

``` text
新增表
字段
FK
索引
CASCADE
Alembic revision
```

## 5. API

列出：

``` text
METHOD
PATH
AUTH
```

## 6. Security

明确说明：

``` text
Audio Owner Isolation
Transcript Owner Isolation
Segment Owner Isolation
IDOR
Cross-user access
Schema injection
```

## 7. Tests

例如：

``` text
pytest xx passed
```

并说明关键测试覆盖。

## 8. Ruff

``` text
ruff check
ruff format --check
```

## 9. Alembic

说明：

``` text
upgrade head
current
heads
check
```

## 10. PostgreSQL Smoke

说明真实 PostgreSQL 是否通过。

## 11. Git

说明：

``` text
commit hash
commit message
working tree
```

## 12. Technical Debt

只记录真实发现，不为了报告好看而制造问题。

------------------------------------------------------------------------

# 四十、最终验收门槛

Part 9.5 只有在以下全部满足时，才可以报告：

``` text
PASS
```

必须：

``` text
[ ] AudioRecording 完成
[ ] Transcript 完成
[ ] TranscriptSegment 完成
[ ] InterviewMessage 最小扩展完成
[ ] Owner Isolation 完成
[ ] IDOR 测试通过
[ ] PostgreSQL 通过
[ ] Alembic 通过
[ ] pytest 全部通过
[ ] ruff 全部通过
[ ] format check 通过
[ ] 无真实 secret
[ ] Git diff scope 正确
[ ] Part 9.4 历史 commit 未修改
[ ] 未实现 Memory/RAG/Memoir/LLM/Agent
```

如果存在 Medium 风险但不阻塞：

``` text
PASS WITH FINDINGS
```

如果存在 Critical / High，或数据库迁移 / Owner Isolation /
测试基础设施失败：

``` text
BLOCKED
```

不得为了通过验收而隐藏问题。

------------------------------------------------------------------------

# 四十一、最重要的执行原则

整个任务只遵守一句话：

> **先理解现有 Part 9.4，再按照 Part 9.5
> 设计基线做最小增量实现；不要提前实现后面的 AI 系统。**

尤其不要：

``` text
为了 Audio → 提前做 Memory
为了 STT → 提前做 AI Agent
为了 Transcript → 提前做 RAG
为了 Message → 提前做 LangGraph
为了 Object Storage → 提前搭完整云基础设施
```

本阶段真正要建立的是：

``` text
稳定的数据基础设施：

Session
   ↓
Audio
   ↓
Transcript
   ↓
Segment
   ↓
Message
```

未来 AI 系统建立在这条稳定链路之上。

------------------------------------------------------------------------

# 四十二、任务结束定义

当以下状态同时成立：

``` text
Part 9.4
        ↓
设计基线
        ↓
Part 9.5
        ↓
Audio
        ↓
Transcript
        ↓
TranscriptSegment
        ↓
Message integration
```

且：

``` text
数据库正确
API 正确
Owner Isolation 正确
测试通过
Migration 正确
Git 干净
```

才视为：

> **Part 9.5 Audio / STT 数据基础设施实施完成。**
