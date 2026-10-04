# ADR-002 User删除策略

## 状态

Proposed

## 背景

当前存在级联关系：

User ↓ Family ↓ FamilyMember ↓ Interview ↓ Session ↓ Audio ↓ Transcript
↓ Segment

部分关系使用CASCADE。

## 风险

未来如果直接删除User：

可能导致整个人生记录树被删除。

## 当前决定

暂不修改数据库。

等待产品确认：

1.  用户删除是否允许？
2.  是否软删除？
3.  是否数据归档？
4.  是否需要保留历史人生数据？

## 后续处理

确定策略后：

-   修改Foreign Key策略
-   增加删除流程
-   更新ADR
