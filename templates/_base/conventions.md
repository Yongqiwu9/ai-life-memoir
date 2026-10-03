# Templates 通用约定

## 目录与命名

统一使用：

```text
templates/<domain>/<template-name>/
```

例如 `templates/backend/fastapi-crud/`、`templates/ai/rag/`。

模板内部按需包含：`README.md`、`AGENTS.md`、`template/`、`tests/`、`examples/`。
不要为了形式而创建无意义的空实现。

## 分层约定

### Backend

```text
Router -> Service -> CRUD -> Model
          \-> Schema
Dependency
Test
```

- Router：只处理 HTTP、参数、依赖注入与响应。
- Service：业务规则与事务边界。
- CRUD：数据库访问，不含业务规则。
- Model：SQLAlchemy 映射。
- Schema：API 输入/输出。
- Dependency：认证/权限等可复用依赖。

命名：模型 `PascalCase`（如 `Memory`）；Schema 用 `<Resource>Create / Update / Read`；
CRUD 用 `<Resource>CRUD`；Service 用 `<Resource>Service`；路由用 `<resource>_router`。

### Frontend

```text
Page / List / Detail / Form / API / Store / Component
```

### AI

```text
Agent / Prompt / Workflow / Provider / RAG / Embedding / Fact Checker
```

### Infrastructure

```text
Docker / Nginx / GitHub Actions
```

## 占位符规则

- 资源名占位：`<resource>`、`<Resource>`、`resource`。
- 配置占位：`<your-secret>`、`<your-api-key>`、`user:password@localhost/dbname`。
- 需要替换的临时实现必须显式标注 `TEMPLATE ONLY`。

## 安全规则

- 禁止真实 secret、真实生产 URL、真实 token。
- 模板中的认证示例必须是占位实现，并提示替换为项目真实依赖。
