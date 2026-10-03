# Templates AGENTS

本文件是 `templates/` 目录的统一规则。

1. `templates` 是代码生成模板库（Mother Code），不是运行时代码。
2. `templates` 不参与 Runtime，不允许被 `apps/`、`services/`、`packages/` import。
3. 模板不得包含真实密码、API Key、JWT Secret、Token 或其它 secret。
4. 模板不得包含真实生产 URL；连接串/密钥一律使用 placeholder。
5. 示例配置必须使用 `postgresql://user:password@localhost/dbname`、`<your-secret>` 之类的占位值。
6. 修改模板必须验证模板自身（`compileall`、secret 扫描、最小示例）。
7. 模板必须保持最小依赖，不引入与示例无关的重量级依赖。
8. 模板不得依赖具体业务模块（如固定的 memory/family/interview 领域命名，除非仅作示例说明）。
9. 模板中的变量/占位符必须明确，例如 `<resource>`、`<Resource>`、`resource`。
10. Codex 生成新业务模块时，应优先查找并复用对应模板，而不是从零编写。
