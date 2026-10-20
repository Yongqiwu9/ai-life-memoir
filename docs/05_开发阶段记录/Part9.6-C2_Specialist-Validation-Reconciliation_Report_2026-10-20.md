# Part 9.6-C2 — 专项验证对账与结果收尾报告

- 日期：2026-10-20（Asia/Shanghai）。
- 结论：**LOCAL SPECIALIST VALIDATION PASS / CLEANUP CONFIRMED**。
- C2 状态：实施已写入；本地合成 HTTP/ASGI 与隔离 PostgreSQL 专项证据闭环。**NOT SEALED / Git 与完整合同封板对账待完成**。
- 执行基线：`master @ c8824b3c2c1d7c9ae6d633461787431166cd7a07` 加已授权工作区；不是新 commit 或远程 CI 结论。
- 详细证据：[专项证据 JSON](Part9.6-C2_Specialist-Validation-Evidence_2026-10-20.json)。原[验证合同](Part9.6-C2_HTTP-ASGI-PostgreSQL16.15_Validation-Contract_V1.0.md)保留冻结时原文及 NOT RUN 历史，不改写为当时已执行。

## 1. 范围与对账方法

本轮只复审当前父行锁单用例，执行一次新库 PG 专项，对账并同步文档。未扩建启动平台、未重复 HTTP、未运行完整 Fast/AI Service suite，未暂存、提交或推送。

执行前361项输入哈希匹配；PG脚本、全部固定节点、逐节点JUnit、退出收据及清理证据逐项对应。归档的 inputs_at_execution 是运行时快照；后续三份入口文档的同步不回写这份历史快照或假称重新执行。竞争13项是运行17项的子集，不相加为30项。

## 2. 结果与证据边界

| 验证 | 结果 | 执行时点与范围 |
| --- | --- | --- |
| Backend HTTP/ASGI | 48 PASS | 2026-10-19既有合成Router级证据，本轮未重跑 |
| AI Service HTTP/ASGI | 6 PASS | 同上，独立应用及合成credential/Stub |
| PostgreSQL | 16.15 / server_version_num=160015 | 本轮现场核验既有容器/镜像/端口/集群精确身份 |
| Fresh upgrade / current / check | PASS | 新唯一临时库，精确head `c296a4e8d102` |
| Manager迁移 | 4 PASS | Legacy升级、marker回退拒绝、旧结构回退再升级、metadata一致 |
| Runner运行 | 17 PASS | 0 failed / errors / skipped；精确节点一致 |
| 其中竞争 | 13 PASS | 独立连接、实际事务及各用例原有同步/竞争断言；零跳过 |
| Post-integration current / check | PASS | 运行后按同一精确head核验 |
| 清理 | PASS | 新库/角色/会话为零，HBA逐字节恢复 |

HTTP原始目录`run-a27a2364e7aa4477b6079eb30541f410`保留；Manager可读副本按六文件SHA256与原转存清单一致，副本不是新测试。历史HTTP报告中的“PG NOT RUN”仍是该次执行范围，本次PG结果独立记录，不回写历史。

## 3. 单用例修正与独立复审

`tests/integration/test_dialogue.py::test_parent_lock_sequence` 单函数修正：移除PID查询后预备commit，使实际业务加锁使用同一连接事务；显式收集成功结果与脱敏异常；观测writer PID，要求wait_event_type=Lock且pg_blocking_pids包含holder PID；holder释放后有界join，退出不确定仍UNKNOWN/保留。5/3/10秒上限及写入/消息序号断言保持。

独立只读定向复审：`/root/parent_lock_fix_review`，**PASS**。复审人未执行测试或数据库。测试文件SHA256：`31d41ce752440352cce0914595dabc182202e691f301d401925b6485f35561a2`。Ruff/format按Backend配置PASS；不是全仓lint或全量测试结果。

本轮真实PG中该用例PASS。旧失败只能证明原测试未观察到等待；不能据此将业务加锁判为失效，也不能从新PASS反推旧轮次发生了哪次连接切换。

## 4. 迁移4项

- `test_legacy_upgrade`：PASS。
- `test_marker_downgrade_refusal`：PASS。
- `test_legacy_downgrade_reupgrade`：PASS。
- `test_schema_matches_metadata`：PASS。

旧表反射造数显式提供User.is_active与Interview.type。旧v1/v2 State/Turn/Message保持断言和新字段NULL断言通过；不补认历史Consent。Migration源码未因本次收尾修改。

## 5. Runner17项与竞争13项

| 精确节点 | 竞争子集 | 本轮 |
| --- | --- | --- |
| test_runtime_column_constraints | 否 | PASS |
| test_runner_is_restricted | 否 | PASS |
| test_parent_lock_sequence | 是 | PASS |
| test_parallel_same_key | 是 | PASS |
| test_normal_cas_race | 是 | PASS |
| test_stop_publish_race | 是 | PASS |
| test_typing_delivery_race | 是 | PASS |
| test_claim_crash_once | 否 | PASS |
| test_delivery_unknown_readback | 否 | PASS |
| test_source_publish_race | 是 | PASS |
| test_parent_child_preparing | 是 | PASS |
| test_old_generation_after_stop_cannot_poison_new[ready] | 是 | PASS |
| test_old_generation_after_stop_cannot_poison_new[timeout] | 是 | PASS |
| test_unknown_first_cannot_be_cleared_by_other_connection | 是 | PASS |
| test_callback_publication_vs_delivery | 是 | PASS |
| test_pause_rpc_vs_later_safety_control[typing_started] | 是 | PASS |
| test_pause_rpc_vs_later_safety_control[record_only] | 是 | PASS |

逐节点退出码0、单节点JUnit无failure/error/skipped，对应收据threads=0、children_confirmed=true、retained=false。父行锁用例的PASS包含writer锁等待、holder阻塞者匹配、退出及最终序号断言；归档不声称另外采集了未保存的完整SQL trace或每个同步瞬间的PID流水。

## 6. 分配、权限与清理

- Run UUID：`eb00aa2b-d934-421b-817f-def5a55f8b24`。
- 容器：`1e4f6a0a344c9eee9de80847b66e096fc5bfa76a2854faa485b7bb81ce80db73`；集群system_identifier：`7694724439064498215`。
- 临时库：`ai_memoir_dialogue_ci_test_eb00aa2bd934421b817fdef5a55f8b24`，OID70444。
- 专属owner OID70442、Runner OID70443；Manager迁移与受限Runner分离。Runner无超级用户、建库/建角色、角色成员及CREATE/TEMP/schema CREATE权限的用例通过。
- 本次Runner仅获本次新库连接，postgres/template1/历史库实际连接拒绝；原历史库ACL和角色不变。local HBA证据不冒称CI独占集群SQL ACL撤销。
- Manager state=CLEANED、lock_exit=0；全部控制进程退出并确认EOF。独立按精确名称和OID核验database_rows=0、role_rows=0、sessions=0、runner_hba_rules=0。
- 原HBA与恢复后文件逐字节相等，SHA256 `af0fdb739b67d1a552cd82c19311b813e753d4f651a61e6b563f48b55dca5e74`。没有FORCE、任意kill、容器重建或生命周期操作。

## 7. 历史失败与限制

旧运行目录和报告均保留：Legacy造数、inet文本带掩码、OID凭证类型、原父行锁观测及诊断轮次不擦除。外部脚本仅完成专项诊断/查询格式/凭证类型等已批准修正，不作为通用平台；三个OID只在allocation.json副本中写为整数，不弱化精确身份断言或Manager内部清理比较。

**不据本报告关闭：** D01–D73完整代码/测试/执行证据逐项封板对账、exact C2 commit的远程CI、Git闭环；真实语音/STT/TTS、真实Provider/费用能力、真实个人资料、资料集/多来源、C3激活/C4 Consent/C6删除流程、生产及旧UNKNOWN/BM-01。HTTP仅合成Router级，不代表完整JWT、真实Consent或生产部署端到端验证。

## 8. 收尾状态

本地专项执行证据无剩余失败/清理未知；不自动宣布C2 Completed/Sealed。本轮新增本报告和脱敏证据JSON，必要同步README/路线图/开发日志；保留历史合同与审查原文及既有C3/BM-01改动。16项模板删除、ad和ignored .env.test不触碰；无Git写操作。

下一门禁：审查本轮测试修正与专项文档差集，完成完整合同封板对账及精确候选文件审计；暂存/提交/推送仍须分别授权。不新增功能或重复已有HTTP执行。
