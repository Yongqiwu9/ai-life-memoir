# Templates — Code Generation Library

`templates/` 是本项目的“母版 / 代码生成库”。它保存可以被 Codex 读取、复制、改造，
用于生成新业务模块的标准化模板。它**不是**运行时代码。

## 1. Templates 的目的

- 固化已验证的分层结构与实现范式，让后续模块（Part 9.3、9.4、9.5……）复用同一套骨架。
- 降低每次新建模块时的重复设计与不一致风险。
- 作为 Codex 生成 `Router -> Service -> CRUD -> Model -> Schema` 代码时的权威参考。

## 2. Templates 与 Runtime 的区别

| 维度 | templates/ | apps/ / services/ / packages/ |
| --- | --- | --- |
| 角色 | Mother Code / 代码生成库 | Runtime Product / 运行产物 |
| 是否被 import | 不允许 | 允许（应用内部） |
| 是否可直接运行 | 不一定 | 是 |
| 是否包含真实 secret | 禁止 | 仅通过环境/.env 注入 |

## 3. Codex 如何使用 Templates

1. 开发新模块前，先查找 `templates/<domain>/<template-name>/` 是否有对应模板。
2. 复制模板到目标模块路径，仅替换业务字段、类名、路由与业务规则。
3. 保持模板约定的分层与公共依赖不变。
4. 模板中带 `TEMPLATE ONLY` 标记的占位实现，必须替换为项目的真实基础设施（例如 JWT 依赖）。

## 4. 模板生命周期

- 创建：当一类实现被验证可靠后，抽象为模板归档。
- 使用：复制/改造生成新模块。
- 演进：模板修改必须先验证模板自身，再同步到受影响的生成代码。
- 淘汰：不再适用的模板标记废弃并在 README 说明。

## 5. 新模板如何加入

统一目录结构：

```text
templates/<domain>/<template-name>/
├── README.md        # 用途、结构、如何使用
├── AGENTS.md        # 本模板的 Codex 规则（可选）
├── template/        # 可复制的骨架代码
├── tests/           # 模板测试（可选）
└── examples/        # 使用示例（可选）
```

## 6. 模板如何验证

- 对含 Python 的模板执行 `python -m compileall templates/`。
- 对模板自身做 secret 扫描（见下）。
- 确认模板不 import `apps/`、`services/` 等运行时代码。
- 通过一个最小示例验证模板可以复制后运行/通过测试。

## 7. 模板不得被 Runtime import

禁止在运行时出现：

```python
from templates import ...
import templates.xxx
```

也不得把 `templates/` 加入 `PYTHONPATH` 或作为 `apps/backend` 的依赖。

## 8. 模板修改必须经过验证

任何模板改动都要：

- 说明改动原因；
- 用 `compileall` 或最小示例验证；
- 检查是否影响既有生成约定。

## 9. 模板必须保持可复制性

- 模板之间尽量低耦合；
- 依赖最小化；
- 不引用具体业务模块；
- 变量/占位符必须明确标注（如 `<resource>`、`<Resource>`）。

## 10. 模板不能包含真实 secret

禁止出现真实 `DATABASE_URL`、`JWT_SECRET_KEY`、`OPENAI_API_KEY`、`AWS_SECRET_ACCESS_KEY`、
密码或 `Authorization: Bearer <token>`。示例配置一律使用 placeholder。
