# Codex Rules — FastAPI CRUD Template

## 1. Architecture

必须遵循：

Router -> Service -> CRUD -> Model
       -> Schema

禁止：
- Router 中直接编写复杂数据库逻辑
- Service 中散落 SQL 查询
- CRUD 层处理业务规则
- 为单个模块重新发明 CRUD 基础结构

## 2. Naming

- Python 文件：snake_case
- Model：PascalCase，例如 Memory
- Schema：`MemoryCreate` / `MemoryUpdate` / `MemoryRead`
- CRUD：`MemoryCRUD`
- Service：`MemoryService`
- Router：`memory_router`

## 3. Database

- SQLAlchemy 2.x style
- 使用 `Mapped[]` + `mapped_column()`
- 主键默认 UUID
- 时间字段使用 UTC
- 不允许把数据库密码写入源码

## 4. API

默认 REST：

POST   /resources
GET    /resources
GET    /resources/{id}
PATCH  /resources/{id}
DELETE /resources/{id}

列表接口必须支持：
- page
- page_size

默认：
page=1
page_size=20

## 5. Error Handling

资源不存在统一返回 404。
非法输入由 Pydantic/FastAPI 处理。
不要返回裸数据库异常。

## 6. Security

涉及 user_id 的资源必须经过当前用户身份校验。
禁止客户端自行决定 owner/user_id。

## 7. New Module Workflow

复制本模板后，只修改：
1. Model 字段
2. Schema 字段
3. CRUD 类名
4. Service 类名
5. Router 路径
6. 业务规则
7. 测试

不要修改公共基础设施，除非确有必要。
