# _base — 模板通用规范

`_base/` 存放所有模板共享的基础约定与分类规则。它不是某个可复制的代码模板，
而是 Codex 生成和校验各领域模板时的统一基线。

## 内容

- `AGENTS.md`：维护 `_base` 约定自身的规则。
- `conventions.md`：Backend / Frontend / AI / Infrastructure 的分类与命名约定。

## 使用方式

各领域模板的 `README.md` / `AGENTS.md` 应遵守 `_base/conventions.md` 中的约定；
当约定需要变更时，先修改 `_base`，再评估是否影响既有模板。
