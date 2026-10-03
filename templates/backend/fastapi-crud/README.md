# FastAPI CRUD 模板

> 归档自 `docs/AI人生回忆录平台_Codex模板库_V1_Part1_FastAPI_CRUD`。

本模板用于快速创建标准业务模块，例如：

- memories
- interviews
- chapters
- orders
- subscriptions

标准分层：

```text
Router -> Service -> CRUD -> SQLAlchemy Model
             |
           Schema
```

原则：

1. Router 只负责 HTTP / 参数 / 权限依赖。
2. Service 负责业务规则和事务边界。
3. CRUD 负责数据库 CRUD。
4. Schema 负责 API 输入输出。
5. Model 负责数据库映射。
6. 新模块优先复制本模板，不重复生成基础 CRUD。

## 结构

```text
template/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── deps.py
│   │   └── v1/memories.py
│   ├── core/config.py
│   ├── crud/memory.py
│   ├── db/session.py
│   ├── models/base.py
│   ├── models/memory.py
│   ├── schemas/memory.py
│   └── services/memory.py
├── tests/test_memory_api.py
├── pyproject.toml
└── .env.example
```

模板中以 `memory` 命名的文件是**示例资源**，复制生成新模块时应替换为 `<resource>`，
并按 `_base/conventions.md` 的命名规则改名。
