# Database Schema Evolution_V1.0

> 下文 V1–V4 及数据库原则记录既有数据库基线。Part 9.5.5-C 的详细冻结设计见：[Family Collaboration / Participant / Consent Design Freeze V1.0](../03_业务流程/Part9.5.5-C_Family-Collaboration-Participant-Consent_Design-Freeze_V1.0.md)（DESIGN FROZEN / IMPLEMENTATION NOT STARTED）。
> 新增实体、FK 调整、历史资料 fail closed、来源及删除传播的迁移设计以该 SSOT 为准；尚未创建或执行 C 的 Migration。既有 CASCADE 声明不能代替冻结的生命周期政策。

## V1 基础模型

User

作为所有资源归属根节点。

## V2 Family模型

新增：

families

family_members

关系：

User \| Family \| FamilyMember

## V3 Interview模型

新增：

interviews

interview_sessions

interview_messages

关系：

FamilyMember \| Interview \| Session \| Message

## V4 Audio/STT模型

新增：

audio_recordings

transcripts

transcript_segments

关系：

Session \| AudioRecording \| Transcript \| TranscriptSegment

Message扩展：

source

transcript_segment_id

## 当前数据库原则

-   UUID主键
-   外键约束
-   时间字段timezone-aware
-   Owner Isolation
-   级联删除策略待最终确认
