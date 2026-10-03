# Codex Commands

## 创建新 CRUD 模块

复制：

`template/app/models/memory.py`
`template/app/schemas/memory.py`
`template/app/crud/memory.py`
`template/app/services/memory.py`
`template/app/api/v1/memories.py`

然后要求 Codex：

> 根据 FastAPI CRUD 模板创建 [MODULE] 模块。
> 只修改业务字段、类名、路由和业务规则。
> 保持 Model -> Schema -> CRUD -> Service -> Router 分层。
> 不要修改公共数据库依赖和认证基础设施。
> 同时生成 Alembic migration 和 pytest 测试。

## 创建 Chapter

示例要求：

> 使用 FastAPI CRUD 模板创建 Chapter 模块。
> 字段：
> - user_id
> - title
> - content
> - sort_order
> - status
> - published_at
> Chapter 必须只能访问当前用户自己的数据。

## 创建 Interview

> 使用 FastAPI CRUD 模板创建 Interview 模块。
> 字段：
> - user_id
> - session_id
> - question
> - answer
> - audio_url
> - transcript
> - started_at
> - ended_at
> 增加 Interview 与 Memory 的业务关联，但不要破坏基础 CRUD 分层。
