# AI人生回忆录平台 Codex模板库 V1.0
## Part 1：FastAPI CRUD模板

本模板用于快速创建标准业务模块，例如：
- memories
- interviews
- chapters
- orders
- subscriptions

标准分层：

Router -> Service -> CRUD -> SQLAlchemy Model
             |
           Schema

原则：
1. Router 只负责 HTTP / 参数 / 权限依赖。
2. Service 负责业务规则和事务边界。
3. CRUD 负责数据库 CRUD。
4. Schema 负责 API 输入输出。
5. Model 负责数据库映射。
6. 新模块优先复制本模板，不重复生成基础 CRUD。
