# Part 9.6-C1 — 正式独立实现审查报告（初审历史）

## Metadata

- 日期：2026-10-16；基线：`master @ 3873c744eec87af2740731d1098cbd488d145ef2`。
- 原结论：**FAIL（静态审查范围）**；三位未参与实施的审查代理覆盖全部11个新增文件，确认三项P2问题和两项验收证据缺口。
- 本文件归档此前只读初审意见，不是本轮重新审查，不把FAIL改写为PASS。后续用户批准限定修复，最新关闭范围见[修复及定向复审](Part9.6-C1_Remediation-and-Targeted-Review_Report_2026-10-16.md)。
- 审查所依据的11文件SHA-256见[验收元数据的 historical_pre_remediation](Part9.6-C1_Validation-Evidence_2026-10-16.json)；下列行号均是该旧版本定位。

## C1-IR-01 / P2 — 受限来源的AI衍生内容仍可继续使用

原定位：`services/ai-service/app/dialogue/controller.py:211–215`，关联旧238–252、633–640行。

可达顺序：请求R使用来源S → 替换选择时移除S、保留R的assistant历史 → 限制S → 再次请求回应。检查仅比较source_refs，因此仍会读取并向离线Stub传入保留的AI内容，违反合同§19.6。原测试只覆盖先限制、后重建。

原最小修复建议：在计算Context摘要、生成和交付前，通过response_id追踪历史请求依赖，要求清除相关内容后才能继续。影响按C1合成离线范围评定，不据此认定真实权限绕过或默认Mock已经生成新事实。

## C1-IR-02 / P2 — 可用性缺项被默认放行

原定位：`services/ai-service/app/dialogue/contracts.py:163`。

FixtureSource未提供availability时仍默认available，随后可进入生成链路。合同§5将其列为必需字段，并禁止隐藏默认值自动放行。原测试helper始终显式传入字段，未测缺项。

原最小修复建议：移除默认值，补缺项拒绝及两个显式值测试。这是合成离线DTO合同缺陷，不是已验证的真实Consent绕过。

## C1-IR-03 / P2 — Unicode规范化可使合法交付抛异常

原定位：`services/ai-service/app/dialogue/controller.py:483–490`，关联 `contracts.py:374`。

700个U+FB03连字组成的来源可生成不足2000字符的合法问题，但NFKC规范化后超过回执字段的2000字符上限。response_ready已经发出deliver，随后delivery_started构造QuestionReceipt时抛出未处理的ValidationError。

原最小修复建议：在交付前检查派生值容量，或采用与正文限制相容的容量；不能截断后用于去重。原规范化测试仅覆盖全角、大小写和标点，没有长度扩展场景。

## 另两项验收证据缺口

- C52：原 `tests/test_dialogue_controller.py:816–855` 在B未消耗额度时接收A迟到提交，未实际证明B已消耗后不会恢复额度。应补B已消耗额度→A迟到提交→保持语义/静默起点/额度的断言。
- C54：原 `tests/test_dialogue_controller.py:871–899` 只覆盖新请求仍在generating，active_response为NULL；应补新响应ready/delivering时旧ready/failed/completion不改新响应或started receipt，且合法新completion仍能完成。

这两项属于验收不足；静态阅读未确认对应运行代码错误，不将其表述为已复现的权限绕过或数据损坏。

## 原执行证据与安全边界

- 只读核对修复前XML：定向183／全量330，均记载零失败、零错误、零跳过；不是审查人独立执行。
- 审查前后11文件与316既有保护文件哈希未变，暂存区为空，16历史删除、ad与既有内容保持。
- 未改文件、未运行代码探针、测试、应用、HTTP、数据库、Docker或Provider，未执行Git写操作，未读取env/ad/secret。
- 原建议：限定修复三项，补回归和C52/C54断言后定向复审；当时不进入暂存或封板。该后续工作已经另获授权并完成，见后续报告；原意见保留其时点。
