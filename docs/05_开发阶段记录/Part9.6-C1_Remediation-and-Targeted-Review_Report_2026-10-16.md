# Part 9.6-C1 — 修复与定向复审归档（当前结果）

## 当前状态与归档边界

- **合成离线实施及定向复审通过，Git 闭环待完成**；未暂存、未提交、未推送、未封板。
- 本轮仅归档既有修复/复审报告，未重新运行测试；下方“不改文档”等安全陈述专指此前修复阶段，不是本次文档归档操作。
- 原[实施快照](Part9.6-C1_Implementation-and-Validation_Report_2026-10-16.md)及[独立初审FAIL](Part9.6-C1_Independent-Implementation-Review_Report_2026-10-16.md)保留；原合同与合同审查报告不改写。
- 原审查人独立只读定向复审：IR01/IR02（上下文审查）、IR02/IR03（状态机审查）、availability与C52/C54（证据审查）均PASS/CLOSED。关闭限相应修复及直接回归；他们核对代码和执行元数据，未独立执行测试。
- 可移植验收元数据见[Part9.6-C1_Validation-Evidence_2026-10-16.json](Part9.6-C1_Validation-Evidence_2026-10-16.json)。该JSON包含原始XML文件哈希/节点、11文件哈希、58项对账及原关闭意见；不包含原始Provider请求/响应或捕获正文日志。
- 真实语音、真实Provider、Backend/HTTP接入、数据库、C4/C6、生产及旧UNKNOWN限制继续保留；本地350不等于Backend Fast、PostgreSQL或远程CI。

---

## 原修复与定向复审报告（仅整理链接）

# Part 9.6-C1 — Scoped Remediation + Targeted Re-Review Report

## Result

PASS — authorized scoped remediation, actual synthetic offline regression, and targeted independent static re-review.

This is not staging, a commit, a phase seal, or a real-world/production validation.

## Baseline

- Git HEAD remains `master @ 3873c744eec87af2740731d1098cbd488d145ef2`.
- Approved contract SHA-256: `f036874a1c8a3401c73a375bc2e833bd745fcaaebd0f97fadbea329c06a18563`.
- Historical implementation evidence (183 / 330) is preserved. The new evidence below applies to the changed source hashes.

## Actual validation

| Check | Result |
| --- | --- |
| New remediation / missing-assertion cases | 20 passed, 0 skipped |
| Complete C1 synthetic suite | 203 passed, 0 skipped |
| Complete AI Service suite | 350 passed, 0 skipped (203 C1 + 147 existing) |
| Ruff | PASS |
| Format | PASS, 25 app/tests files |

XML execution metadata: [专项20、C1 203、全量350的XML哈希及完整节点](Part9.6-C1_Validation-Evidence_2026-10-16.json). All show 0 failures/errors/skips. No passing-test body logs were captured.

## Targeted review closure

The original independent reviewers inspected the modified code and assertions read-only. They did not independently execute tests. No new direct regression was confirmed within the targeted repair scope.

### C1-IR-01: CLOSED — targeted static review

Metadata-only ancestry precheck before body digest/use; inherited cancellation dependencies survive raw-source selection changes; raw source access remains unchanged.

- [services/ai-service/app/dialogue/controller.py:222](../../services/ai-service/app/dialogue/controller.py#L222)
- [services/ai-service/app/dialogue/controller.py:237](../../services/ai-service/app/dialogue/controller.py#L237)
- [services/ai-service/app/dialogue/controller.py:192](../../services/ai-service/app/dialogue/controller.py#L192)
- [services/ai-service/app/dialogue/controller.py:252](../../services/ai-service/app/dialogue/controller.py#L252)
- [services/ai-service/app/dialogue/controller.py:259](../../services/ai-service/app/dialogue/controller.py#L259)
- [services/ai-service/tests/test_dialogue_controller.py:149](../../services/ai-service/tests/test_dialogue_controller.py#L149)
- [services/ai-service/tests/test_dialogue_controller.py:291](../../services/ai-service/tests/test_dialogue_controller.py#L291)
- [services/ai-service/tests/test_dialogue_controller.py:252](../../services/ai-service/tests/test_dialogue_controller.py#L252)

### C1-IR-02: CLOSED — targeted static review

FixtureSource.availability is required; missing declaration is rejected; explicit available/restricted remain valid.

- [services/ai-service/app/dialogue/contracts.py:161](../../services/ai-service/app/dialogue/contracts.py#L161)
- [services/ai-service/tests/test_dialogue_contracts.py:151](../../services/ai-service/tests/test_dialogue_contracts.py#L151)

### C1-IR-03: CLOSED — targeted static review

Normalized length checked before deliver using the receipt capacity constant; oversize returns controlled INVALID_RESPONSE; no text truncation.

- [services/ai-service/app/dialogue/controller.py:454](../../services/ai-service/app/dialogue/controller.py#L454)
- [services/ai-service/app/dialogue/contracts.py:369](../../services/ai-service/app/dialogue/contracts.py#L369)
- [services/ai-service/tests/test_dialogue_controller.py:328](../../services/ai-service/tests/test_dialogue_controller.py#L328)

### C52 evidence gap: CLOSED — targeted static review

B no_reply consumes its allowance before late A commit; current turn/hint/timer/cycle and consumed flag remain unchanged; later tick creates no extra request.

- [services/ai-service/tests/test_dialogue_controller.py:377](../../services/ai-service/tests/test_dialogue_controller.py#L377)

### C54 evidence gap: CLOSED — targeted static review

Six old-callback x new-ready/delivering combinations retain the real new response and started receipt; subsequent legitimate completion succeeds.

- [services/ai-service/tests/test_dialogue_controller.py:427](../../services/ai-service/tests/test_dialogue_controller.py#L427)

## Exact changed scope

Only these 5 files were changed relative to the reviewed 11-file implementation. The remaining 6 hashes are unchanged.

| File | Current SHA-256 |
| --- | --- |
| `services/ai-service/app/dialogue/contracts.py` | `c22ec0ee8d0c99b4e52b02b5f21a41ef7f5f49e420381d4f4734dfab2c5113df` |
| `services/ai-service/app/dialogue/controller.py` | `d224a039e15277bd10e6fdef91d5c4ebff5e87bb2c2232b63cf7add3fa2fc7a8` |
| `services/ai-service/app/dialogue/runner.py` | `26696e86437cbb70f872438496056af0176be1b2c1f76f3225940d60b22383da` |
| `services/ai-service/tests/test_dialogue_contracts.py` | `f8cd53fbe22bf0a62a254ccc09ae534a4ad1d1d49d6df4fa1c1f103858a73b98` |
| `services/ai-service/tests/test_dialogue_controller.py` | `d9ae66b8f65a71ef4e299c12c12d1a2bc1347f735cc6b8d7ed1093f3a92ac430` |

## Integrity and retained limits

- All 316 protected pre-existing nonsecret files retain their preflight hashes.
- HEAD unchanged; staging empty; no commit or push.
- 16 historical deletions remain unstaged; `ad` remains untracked; `.env.test` remains ignored and unread.
- Existing AGENTS, C3/BM-01 and mixed documentation changes remain unchanged.
- No project documentation, workflow, configuration, Backend, model, migration or database changes.
- No HTTP/ASGI, PostgreSQL, Docker, voice/STT/TTS, real Provider/network or production operation.
- Actual source access still uses Context.sources. Additional dependency refs are metadata for cancellation/withdrawal propagation only.
- This synthetic profile does not implement real Consent, C4/C6, source deletion or production recovery, and does not resolve historical UNKNOWN resources.

Evidence: [验收元数据与定向关闭意见](Part9.6-C1_Validation-Evidence_2026-10-16.json).

## Current boundary

Remediation and targeted re-review are complete. No staging or phase seal has started.
