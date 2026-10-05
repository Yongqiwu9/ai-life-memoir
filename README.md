# AI人生回忆录平台

将用户口述、录音与采访内容整理为可追溯的 Memory，并进一步生成可编辑的人生回忆录。完整录音、AI 与回忆录链路属于目标产品设计。

## 当前阶段

| Part | 状态与交付边界 |
| --- | --- |
| 9.1–9.5 | 基础 Backend / 数据模型与 API 阶段完成：认证、Family/FamilyMember、Interview/Session/Message、Audio/Transcript/Segment 元数据 |
| 9.5.5 | Memory 前置基础设施/架构决策阶段；9.5.5-A 为产品约束与 ADR 文档整理，本轮交付供人工审查 |
| 9.6 | Memory Extraction — Planned；MemoryCandidate、Memory、提取及人工确认流程尚未实现 |

Part 9.5 完成不代表 Audio upload、Object Storage、STT Provider 或 AI pipeline 已完成。当前权限实现为 Owner-only；首版 Family Collaboration 是已确认产品方向，具体权限方案仍为 Proposed。

本轮 ADR-003 Accepted 只冻结 Owner 删除整个 Family Archive 的产品权限。ADR-002、004–009 为 Proposed，包含已确认约束与尚未冻结的设计；已有 ADR-001 保持 Accepted。Accepted 不代表对应功能已实施。

## 项目资料

- [Part 开发路线图](docs/05_开发阶段记录/Part开发路线图_V2.0.md)
- [系统架构总览](docs/01_架构设计/AI人生回忆录平台_系统架构总览_V1.1.md)
- [Audio/STT 数据模型设计基线](docs/02_数据模型/Part9.5_Audio-STT数据模型设计基线_V1.0.md)
- [ADR-003 Family档案删除策略](<docs/06_技术决策记录/ADR/ADR-003 Family档案删除策略.md>)
- [ADR 目录](docs/06_技术决策记录/ADR/)

代码和文档工作遵循 [Root AGENTS.md](AGENTS.md) 与 [Backend AGENTS.md](apps/backend/AGENTS.md)。templates/ 是代码母版，不参与运行时 import。
