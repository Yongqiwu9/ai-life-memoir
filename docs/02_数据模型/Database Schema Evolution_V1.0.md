# Database Schema Evolution_V1.0

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
