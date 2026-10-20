# Part 9.6-C2 — D01–D73验收总对账与最新差集回归

- 日期：2026-10-21（Asia/Shanghai）。
- 结论：**LOCAL DIFFERENTIAL REGRESSION PASS / ACCEPTANCE MAPPED / NOT SEALED**。
- 基线：`master @ c8824b3c2c1d7c9ae6d633461787431166cd7a07` 加已授权工作区；未生成新commit或新远程CI。
- 详细节点、代码路径、哈希与执行范围：[验收证据JSON](Part9.6-C2_Full-Regression-Acceptance-Evidence_2026-10-21.json)。本报告为本会话对账，不冒称新增独立验收审查。

## 1. 执行口径与结果

为遵守“不重复已充分通过的HTTP”，执行前声明采用差集口径：复用未变化的C2专项HTTP，运行其余全部Backend顶层Fast及AI Service全部纯离线文件。未重复专项PG、未操作Docker、未执行真实数据库迁移，也未改动项目源码、测试或workflow。

| 范围 | 结果 | 证据边界 |
| --- | --- | --- |
| Backend Fast差集 | **1008 PASS** | 新执行全部顶层Fast文件，仅排除已有48项的`test_dialogue_api.py`；无failure/error/skipped |
| Backend C2 HTTP | **48 PASS，复用** | 2026-10-19合成ASGI；相关应用、fixture及HTTP测试哈希与已归档输入一致；不是本轮重跑 |
| AI Service纯离线 | **360 PASS** | 新执行七个纯测试文件，包含原C1；不含ASGI六项 |
| AI Service HTTP | **6 PASS，复用** | 同上，2026-10-19既有证据 |
| PostgreSQL16.15 | **迁移4／运行27（其中竞争16）PASS，复用** | 2026-10-20 run `651797b3-a319-44d9-ac7a-5bef75d88b83`；清理确认，不再分配新库 |
| Backend Ruff／format | PASS／195文件 | 与当前workflow指定路径一致的静态检查 |
| AI Service Ruff／format | PASS／30文件 | 当前app/tests静态检查 |
| B／Dialogue纯mock自检 | 43／47 PASS | Backend工作目录；不是实际Linux/PG/remote job结果 |
| Alembic heads | `c296a4e8d102`单一head | 本轮仅脚本检查，无数据库连接；fresh/current/check沿用前次真实PG证据 |

Backend证据合并覆盖1056节点（1008新执行＋48复用），AI覆盖366节点（360新执行＋6复用）；**不能写成此次完整Fast1056／AI366全部新执行**。本地Python3.14.0结果仍需未来CI Python3.12验证。

提交范围另行区分：1008项新执行包含不提交的C3/BM-01合成测试278项（content artifact18、isolated database128、PG adapter132）。拟提交主线及已提交基线的新执行为730项，加复用C2 HTTP48覆盖778项；这是源码推导的候选测试覆盖，不是新远程CI已报778。不得为凑齐本地1056数量而把这三个排除文件纳入提交。AI纯360＋复用HTTP6的覆盖也仍按分日期记录。

本地命令使用一次性外部任务脚本，复用现有fixture与固定纯C1/SQLite/import子进程，不建立通用启动平台。配置仅为合成值，禁读密钥/项目环境文件，禁止外网、真实DB及项目文件写入，允许标准库内部socketpair；现有C3/BM-01测试仅做合成/SQLite/导入断言，不激活真实provisioning。Backend退出码0、线程0、275个子进程退出及通信确认、retained=false。实际证据及脚本哈希见JSON；不是抵御恶意Python的OS安全沙箱声明。

Backend32条警告保留：Starlette/httpx弃用1条，现有Memory测试fixture使用`Base.metadata.sorted_tables`时涉及C2 State/Context循环FK的SQLAlchemy排序警告31条。本次不为消警告改业务、测试或依赖。SQLite通过不证明普通PG回归通过。

## 2. 证据图例

- **U/K**：本轮Backend Fast中的`test_dialogue.py`／`test_dialogue_contracts.py`。
- **A**：本轮AI Service纯离线360项。
- **H/I**：复用Backend48／AI6专项HTTP，保持原日期与来源。
- **P/M**：复用2026-10-20 PG运行27／迁移4；竞争16为运行子集。
- **MOCK**：本轮纯mock自检43／47，不等于实际CI。
- **STATIC**：代码/约束/元数据证明；不是新增测试执行。
- **GATE**：仍待执行或审查接受。每行完整参数化节点、证据路径及限制在JSON中逐项记录。

## 3. D01–D73逐项映射

以下“已关联”表示存在且核对了相应实际证据，**不是将73项整体标PASS或代替独立总审**。同一测试可支撑多个验收点，不能相加为独立测试数。

| ID | 要求 | 代码 | 测试／证据选择器 | 对账状态 |
| --- | --- | --- | --- | --- |
| D01 | 严格wire／类型／大小 | `apps/backend/app/schemas/dialogue.py`<br>`services/ai-service/app/dialogue/wire.py` | `K:test_public_command_rejects_untrusted_fields`<br>`A:test_wire_rejects_invalid_binding_and_extra_fields`<br>`I:test_internal_body_limits_and_validation_privacy` | 本地证据已关联，待总审 |
| D02 | 绑定错配及跨scope拒绝 | `apps/backend/app/services/dialogue_client.py`<br>`services/ai-service/app/dialogue/wire.py` | `K:test_client_rejects_every_header_binding_mismatch`<br>`A:test_wire_rejects_invalid_binding_and_extra_fields`<br>`H:test_asgi_cross_session_resource_binding` | 本地证据已关联，待总审 |
| D03 | 内部认证／默认配置关闭 | `services/ai-service/app/dialogue/http.py`<br>`apps/backend/app/services/dialogue_policy.py` | `I:test_internal_asgi_auth_and_bound_reply`<br>`I:test_internal_default_closed_and_no_error_body_leak`<br>`U:test_cross_owner_and_default_allocation_denied` | 本地证据已关联，待总审 |
| D04 | 纯transition不执行generator | `services/ai-service/app/dialogue/service.py` | `A:test_transition_does_not_execute_generation_effect`<br>`U:test_start_has_no_implicit_generation` | 本地证据已关联，待总审 |
| D05 | 同一C1内核初始化／不可变transition | `services/ai-service/app/dialogue/service.py`<br>`services/ai-service/app/dialogue/controller.py` | `A:test_initialize_wire_calls_same_core_without_generation`<br>`A:test_c02_reducer_keeps_state_context_and_event_immutable` | 本地证据已关联，待总审 |
| D06 | 内部错误脱敏 | `services/ai-service/app/dialogue/http.py`<br>`apps/backend/app/core/dialogue_http.py` | `I:test_internal_default_closed_and_no_error_body_leak`<br>`H:test_asgi_all_privacy_boundaries_have_fixed_errors` | 本地证据已关联，待总审 |
| D07 | Owner／Family／Session隔离 | `apps/backend/app/crud/dialogue.py`<br>`apps/backend/app/services/dialogue.py` | `U:test_cross_owner_and_default_allocation_denied`<br>`H:test_asgi_all_routes_foreign_owner`<br>`H:test_asgi_cross_session_resource_binding` | 本地证据已关联，待总审 |
| D08 | 拒绝客户端伪造synthetic／Consent／Provider | `apps/backend/app/schemas/dialogue.py`<br>`apps/backend/app/services/dialogue_policy.py` | `K:test_public_command_rejects_untrusted_fields`<br>`U:test_cross_owner_and_default_allocation_denied` | 本地证据已关联，待总审 |
| D09 | 仅已分配Session可处理 | `apps/backend/app/services/dialogue_policy.py`<br>`apps/backend/app/services/dialogue.py` | `U:test_cross_owner_and_default_allocation_denied`<br>`H:test_asgi_cross_session_resource_binding` | 本地证据已关联，待总审 |
| D10 | 旧v1/v2保留及旧写入口拒绝 | `apps/backend/app/services/interview_message.py`<br>`apps/backend/app/services/interview_agent.py`<br>`apps/backend/alembic/versions/c296a4e8d102_session_text_dialogue.py` | `U:test_old_writers_cannot_bypass_dialogue_profile`<br>`M:test_legacy_upgrade`<br>`K:test_storage_and_integration_versions_fit_distinct_columns` | 本地证据已关联，待总审 |
| D11 | State完整字段分区／重建 | `apps/backend/app/services/dialogue_checkpoint.py` | `K:test_split_merge_of_idle_state_preserves_all_fields`<br>`U:test_split_merge_exact_and_extra_leaf_rejected` | 本地证据已关联，待总审 |
| D12 | 缺失／孤儿／额外叶拒绝 | `apps/backend/app/services/dialogue_checkpoint.py` | `U:test_split_merge_exact_and_extra_leaf_rejected` | 本地证据已关联，待总审 |
| D13 | 依赖预检先于正文／敏感SELECT | `apps/backend/app/services/dialogue_checkpoint.py` | `U:test_restricted_checkpoint_never_selects_sensitive_or_content`<br>`U:test_source_metadata_failure_precedes_sensitive_select` | 本地证据已关联，待总审 |
| D14 | 重启精确Context／label／历史交付状态 | `apps/backend/app/services/dialogue_checkpoint.py` | `U:test_restart_context_preserves_summary_label_and_frozen_started_history` | 本地证据已关联，待总审 |
| D15 | 来源缺失／改变先于Provider拒绝 | `apps/backend/app/services/dialogue_checkpoint.py`<br>`apps/backend/app/services/dialogue.py` | `U:test_source_metadata_failure_precedes_sensitive_select`<br>`U:test_context_body_fingerprint_change_rejects_without_rpc`<br>`P:test_source_publish_race` | 本地证据已关联，待总审 |
| D16 | 传递AI历史依赖受限 | `apps/backend/app/services/dialogue_checkpoint.py`<br>`services/ai-service/app/dialogue/controller.py` | `U:test_restricted_checkpoint_never_selects_sensitive_or_content`<br>`A:test_ir01_c40_c57_restrict_after_selection_removal_blocks_ai_history_before_hash`<br>`A:test_ir01_c40_c57_removed_raw_source_still_cancels_dependent_history_output` | 本地证据已关联，待总审 |
| D17 | 替换后清除退休叶／不复制Context正文 | `apps/backend/app/services/dialogue_checkpoint.py` | `U:test_split_merge_exact_and_extra_leaf_rejected`<br>`U:test_event_journal_context_never_copies_original_text` | 本地证据已关联，待总审 |
| D18 | 不读取敏感字段的blind purge | `apps/backend/app/crud/dialogue.py`<br>`apps/backend/app/services/dialogue.py` | `U:test_restricted_checkpoint_never_selects_sensitive_or_content` | 本地证据已关联，待总审 |
| D19 | 损坏checkpoint下metadata GET | `apps/backend/app/services/dialogue.py` | `U:test_checkpoint_sensitive_tamper_detected_after_gate`<br>`U:test_command_readback_is_metadata_only_without_repair` | 本地证据已关联，待总审 |
| D20 | Message单版本来源投影／不伪造Artifact | `apps/backend/app/services/dialogue.py`<br>`services/ai-service/app/dialogue/wire.py` | `U:test_text_original_and_event_then_explicit_apply`<br>`U:test_event_journal_context_never_copies_original_text`<br>`A:test_wire_rejects_invalid_binding_and_extra_fields` | 本地证据已关联，待总审 |
| D21 | 原文／binding／queued Turn原子提交 | `apps/backend/app/services/dialogue.py` | `U:test_text_original_and_event_then_explicit_apply`<br>`U:test_input_atomic_rollback_each_write_boundary` | 本地证据已关联，待总审 |
| D22 | 各输入写边界回滚 | `apps/backend/app/services/dialogue.py` | `U:test_input_atomic_rollback_each_write_boundary` | 本地证据已关联，待总审 |
| D23 | 故障时已保存原文＋queued语义 | `apps/backend/app/services/dialogue.py` | `U:test_pause_outage_preserves_input_and_resume_does_not_generate`<br>`U:test_pure_transition_explicit_retry_preserves_event` | 本地证据已关联，待总审 |
| D24 | apply重放不重复原文 | `apps/backend/app/services/dialogue.py` | `U:test_text_original_and_event_then_explicit_apply`<br>`P:test_saved_source_recovery` | 本地证据已关联，待总审 |
| D25 | 旧text／transcript入口不能绕过 | `apps/backend/app/services/interview_message.py` | `U:test_old_writers_cannot_bypass_dialogue_profile` | 本地证据已关联，待总审 |
| D26 | 父行锁／Message序号 | `apps/backend/app/crud/interview_message.py`<br>`apps/backend/app/crud/dialogue.py` | `P:test_parent_lock_sequence` | 本地证据已关联，待总审 |
| D27 | 同key并发只写一份Message／Turn | `apps/backend/app/services/dialogue.py` | `P:test_parallel_same_key` | 本地证据已关联，待总审 |
| D28 | 载荷冲突／历史HMAC key轮换 | `apps/backend/app/services/dialogue.py`<br>`apps/backend/app/services/dialogue_policy.py` | `U:test_same_key_replay_and_payload_conflict`<br>`U:test_public_apply_binds_key_and_payload_without_redispatch`<br>`U:test_rotated_key_replay_requires_original_key_and_exact_payload` | 本地证据已关联，待总审 |
| D29 | RPC前持久化stop fence | `apps/backend/app/services/dialogue.py` | `U:test_context_child_preemption_returns_parent_identity`<br>`P:test_stop_publish_race`<br>`P:test_parent_child_preparing` | 本地证据已关联，待总审 |
| D30 | RPC故障pause与显式同步 | `apps/backend/app/services/dialogue.py` | `U:test_pause_outage_preserves_input_and_resume_does_not_generate`<br>`U:test_pending_pause_survives_later_safety_control`<br>`P:test_pause_rpc_vs_later_safety_control` | 本地证据已关联，待总审 |
| D31 | 暂停中原文仍可入队 | `apps/backend/app/services/dialogue.py` | `U:test_pause_outage_preserves_input_and_resume_does_not_generate`<br>`H:test_asgi_pause_text_resume_end_lifecycle` | 本地证据已关联，待总审 |
| D32 | resume按序非生成同步 | `apps/backend/app/services/dialogue.py` | `U:test_input_before_pending_pause_preserves_effective_pause_during_drain`<br>`U:test_pause_outage_preserves_input_and_resume_does_not_generate`<br>`H:test_asgi_pause_text_resume_end_lifecycle` | 本地证据已关联，待总审 |
| D33 | 重复pause不恢复额度／不双推进 | `apps/backend/app/services/dialogue.py` | `U:test_repeated_pause_revokes_unpublished_resume_without_new_core_event` | 本地证据已关联，待总审 |
| D34 | blocked／无checkpoint下end无RPC及正文读 | `apps/backend/app/services/dialogue.py`<br>`apps/backend/app/crud/dialogue.py` | `U:test_restricted_checkpoint_never_selects_sensitive_or_content`<br>`U:test_end_is_terminal_and_no_rpc`<br>`U:test_current_generation_unknown_blocks_all_new_generation` | 本地证据已关联，待总审 |
| D35 | end作废queued输入／控制／effect | `apps/backend/app/services/dialogue.py` | `U:test_command_readback_is_metadata_only_without_repair`<br>`P:test_stale_coordinator_reply` | 本地证据已关联，待总审 |
| D36 | record_only／typing屏障 | `apps/backend/app/services/dialogue.py` | `U:test_pending_pause_survives_later_safety_control`<br>`P:test_pause_rpc_vs_later_safety_control`<br>`P:test_typing_delivery_race` | 本地证据已关联，待总审 |
| D37 | Session结束后拒绝新原文 | `apps/backend/app/services/dialogue.py`<br>`apps/backend/app/services/interview_message.py` | `U:test_end_is_terminal_and_no_rpc`<br>`H:test_asgi_pause_text_resume_end_lifecycle` | 本地证据已关联，待总审 |
| D38 | 逻辑时钟重启／回退／旧timer | `apps/backend/app/services/dialogue.py` | `U:test_logical_clock_restart_and_stale_version`<br>`U:test_pure_transition_explicit_retry_preserves_event`<br>`U:test_old_silence_cycle_does_not_generate_after_new_activity` | 本地证据已关联，待总审 |
| D39 | UNKNOWN拒绝重调／new key | `apps/backend/app/services/dialogue.py` | `U:test_current_generation_unknown_blocks_all_new_generation`<br>`P:test_unknown_first_cannot_be_cleared_by_other_connection` | 本地证据已关联，待总审 |
| D40 | 普通旧version拒绝，安全停止例外 | `apps/backend/app/services/dialogue.py` | `U:test_logical_clock_restart_and_stale_version`<br>`P:test_normal_cas_race`<br>`P:test_stop_publish_race` | 本地证据已关联，待总审 |
| D41 | 普通CAS竞争无丢更新 | `apps/backend/app/services/dialogue.py`<br>`apps/backend/app/crud/dialogue.py` | `P:test_normal_cas_race` | 本地证据已关联，待总审 |
| D42 | stop对reserve／ready发布竞争 | `apps/backend/app/services/dialogue.py` | `P:test_stop_publish_race`<br>`P:test_callback_publication_vs_delivery` | 本地证据已关联，待总审 |
| D43 | 输入与delivery-start竞争 | `apps/backend/app/services/dialogue.py` | `P:test_typing_delivery_race` | 本地证据已关联，待总审 |
| D44 | effect claim后故障不能重调 | `apps/backend/app/services/dialogue.py` | `P:test_claim_crash_once` | 本地证据已关联，待总审 |
| D45 | delivery提交不确定读回不重复 | `apps/backend/app/services/dialogue.py` | `P:test_delivery_unknown_readback` | 本地证据已关联，待总审 |
| D46 | prepare到publish间来源失效 | `apps/backend/app/services/dialogue.py`<br>`apps/backend/app/services/dialogue_checkpoint.py` | `P:test_source_publish_race`<br>`P:test_stale_coordinator_reply` | 本地证据已关联，待总审 |
| D47 | delivery token／scope／正文门禁 | `apps/backend/app/services/dialogue.py` | `H:test_asgi_expired_delivery_token`<br>`H:test_asgi_restricted_source_prevents_delivery`<br>`H:test_asgi_cross_session_resource_binding` | 本地证据已关联，待总审 |
| D48 | 重放／迟到结果不复活 | `apps/backend/app/services/dialogue.py` | `U:test_stop_first_old_unknown_does_not_block_new_generation`<br>`P:test_old_generation_after_stop_cannot_poison_new`<br>`H:test_asgi_pending_generation_late_result_after_end` | 本地证据已关联，待总审 |
| D49 | 旧completion不能完成新response | `apps/backend/app/services/dialogue.py` | `U:test_old_completion_cannot_mutate_new_response` | 本地证据已关联，待总审 |
| D50 | ready／started／completed／interrupted区别 | `apps/backend/app/services/dialogue.py`<br>`apps/backend/app/services/dialogue_checkpoint.py` | `H:test_asgi_manual_generation_delivery_receipts_and_replay`<br>`U:test_restart_context_preserves_summary_label_and_frozen_started_history` | 本地证据已关联，待总审 |
| D51 | DEBUG两模式各隐私边界 | `apps/backend/app/core/dialogue_http.py` | `H:test_asgi_all_privacy_boundaries_have_fixed_errors`<br>`H:test_asgi_malformed_json_uuid_and_missing_auth` | 本地证据已关联，待总审 |
| D52 | 只读对账不写／不读正文／不调AI／不枚举 | `apps/backend/app/services/dialogue.py` | `U:test_command_readback_is_metadata_only_without_repair`<br>`H:test_asgi_text_command_replay_conflict_and_readback` | 本地证据已关联，待总审 |
| D53 | fresh16.15及精确head/current/check | `apps/backend/alembic/versions/c296a4e8d102_session_text_dialogue.py`<br>`scripts/ci/run_dialogue_postgres.py` | `M:test_schema_matches_metadata` | 本地证据已关联，待总审 |
| D54 | Legacy升级值与NULL兼容 | `apps/backend/alembic/versions/c296a4e8d102_session_text_dialogue.py` | `M:test_legacy_upgrade` | 本地证据已关联，待总审 |
| D55 | downgrade表／字段marker防护 | `apps/backend/alembic/versions/c296a4e8d102_session_text_dialogue.py` | `M:test_marker_downgrade_refusal`<br>`STATIC:D55_GUARD_COVERAGE` | marker执行＋批准的静态证明 |
| D56 | empty／Legacy回退与旧约束恢复 | `apps/backend/alembic/versions/c296a4e8d102_session_text_dialogue.py` | `M:test_legacy_downgrade_reupgrade` | 本地证据已关联，待总审 |
| D57 | 真实约束SQLSTATE与rollback | `apps/backend/alembic/versions/c296a4e8d102_session_text_dialogue.py`<br>`apps/backend/app/models/dialogue_runtime.py`<br>`apps/backend/app/models/interview_agent.py` | `P:test_runtime_column_constraints`<br>`U:test_child_turn_null_reason_rejected_by_sqlite_check`<br>`U:test_live_output_requires_stable_id_in_sqlite_check` | 本地证据已关联，待总审 |
| D58 | 默认expire与独立连接 | `apps/backend/app/services/dialogue.py` | `P:test_parent_lock_sequence`<br>`P:test_coordinator_recovery_boundaries`<br>`P:test_saved_source_recovery` | 本地证据已关联，待总审 |
| D59 | CI缺失／重复／skip／节点归属攻击 | `scripts/ci/run_dialogue_postgres.py`<br>`.github/workflows/backend-ci.yml`<br>`.github/workflows/dialogue-ci.yml` | `MOCK:DIALOGUE_47`<br>`MOCK:B_43` | 本地证据已关联，待总审 |
| D60 | Manager／Runner权限及UNKNOWN停止清理 | `scripts/ci/run_dialogue_postgres.py`<br>`apps/backend/tests/integration/test_dialogue.py` | `P:test_runner_is_restricted`<br>`MOCK:DIALOGUE_47`<br>`STATIC:SUP_IR_01_CLOSURE` | 本轮受控证据；历史UNKNOWN范围保留 |
| D61 | C1＋Backend Fast＋普通PG完整回归 | `apps/backend/tests/conftest.py`<br>`.github/workflows/backend-ci.yml`<br>`.github/workflows/dialogue-ci.yml` | `GATE:LATEST_REGRESSION_AND_ORDINARY_PG` | **待普通PG／exact CI** |
| D62 | 默认关闭／无真实Provider或Consent绕过 | `apps/backend/app/services/dialogue_policy.py`<br>`apps/backend/app/services/dialogue_client.py`<br>`services/ai-service/app/dialogue/http.py` | `U:test_cross_owner_and_default_allocation_denied`<br>`I:test_internal_default_closed_and_no_error_body_leak`<br>`K:test_public_command_rejects_untrusted_fields` | 本地证据已关联，待总审 |
| D63 | 既有工作区／暂存区保护 | `AGENTS.md`<br>`apps/backend/tests/integration/test_dialogue.py` | `STATIC:WORKTREE_AND_HASH_SAFETY` | 本地证据已关联，待总审 |
| D64 | 如实区分scope／UNKNOWN／生产限制 | `docs/05_开发阶段记录/Part9.6-C2_Minimal-Supplement-Reconciliation_Report_2026-10-20.md` | `STATIC:SCOPED_REPORTING` | 本地证据已关联，待总审 |
| D65 | 无新输入连续提问／刷新恢复及碰撞 | `apps/backend/app/services/dialogue.py` | `U:test_two_manual_questions_without_new_text_refresh_once`<br>`U:test_child_key_collision_never_adopts_client_command`<br>`U:test_context_child_preemption_returns_parent_identity`<br>`P:test_coordinator_recovery_boundaries` | 本地证据已关联，待总审 |
| D66 | 实际变化才刷新／两revision精确推进 | `apps/backend/app/services/dialogue.py`<br>`services/ai-service/app/dialogue/controller.py` | `U:test_unchanged_context_has_no_refresh_or_revision_increment`<br>`U:test_two_manual_questions_without_new_text_refresh_once`<br>`P:test_coordinator_recovery_boundaries`<br>`STATIC:CONTEXT_MANIFEST_INCREMENT` | 本地证据已关联，待总审 |
| D67 | stop-first旧ready／timeout不污染G2 | `apps/backend/app/services/dialogue.py` | `U:test_stop_first_old_unknown_does_not_block_new_generation`<br>`P:test_old_generation_after_stop_cannot_poison_new` | 本地证据已关联，待总审 |
| D68 | unknown-first阻塞且安全stop不能清除 | `apps/backend/app/services/dialogue.py` | `U:test_current_generation_unknown_blocks_all_new_generation`<br>`P:test_unknown_first_cannot_be_cleared_by_other_connection` | 本地证据已关联，待总审 |
| D69 | idle／initializing安全与非法事件 | `apps/backend/app/services/dialogue.py` | `U:test_idle_safety_actions_need_no_initialize_rpc`<br>`U:test_idle_forbidden_events_do_not_write_unappliable_commands`<br>`U:test_idle_record_only_is_synchronized_before_later_start` | 本地证据已关联，待总审 |
| D70 | 新head父链／B与Dialogue远程job | `scripts/ci/run_memory_workflow_postgres.py`<br>`scripts/ci/run_dialogue_postgres.py`<br>`apps/backend/tests/integration/test_memory_workflow.py`<br>`.github/workflows/dialogue-ci.yml` | `MOCK:B_43`<br>`MOCK:DIALOGUE_47`<br>`GATE:EXACT_COMMIT_REMOTE_JOBS` | **待exact远程双job** |
| D71 | 完整checkpoint HMAC／受限先拒绝 | `apps/backend/app/services/dialogue_checkpoint.py`<br>`apps/backend/app/services/dialogue_policy.py` | `U:test_checkpoint_sensitive_tamper_detected_after_gate`<br>`U:test_restricted_checkpoint_never_selects_sensitive_or_content` | 本地证据已关联，待总审 |
| D72 | 冻结attempt重放／保存来源pause恢复 | `apps/backend/app/services/dialogue.py` | `U:test_pure_transition_explicit_retry_preserves_event`<br>`U:test_event_journal_context_never_copies_original_text`<br>`P:test_saved_source_recovery`<br>`P:test_coordinator_recovery_boundaries` | 本地证据已关联，待总审 |
| D73 | 真实PG父子协调全边界／抢占／迟到 | `apps/backend/app/services/dialogue.py`<br>`apps/backend/tests/integration/test_dialogue.py` | `P:test_coordinator_recovery_boundaries`<br>`P:test_saved_source_recovery`<br>`P:test_stale_coordinator_reply`<br>`P:test_parent_child_preparing` | 本地证据已关联，待总审 |


## 4. 证明与剩余门禁

### D55：批准的差集收敛

本轮只读AST再次核对：五张新表均在GUARD_SQL的EXISTS防护内；State10／Turn15个新增字段均有IS NOT NULL防护；downgrade依次取得连接、排他锁、检查并拒绝、再DDL。实际marker拒绝和合法回退再升级沿用PG迁移4项。父约束已覆盖的指针/引用分支不制造非法孤儿、不禁用FK、不新建迁移；不声称每个不可能状态均已单独执行。

### D60、D65、D72、D73：不扩大故障验证范围

SUP-IR-01只关闭新增P03两个Session的强引用/UNKNOWN不关闭问题，修复后的27项真实PG通过不表示历史同型路径全部已整改，也不表示已穷尽真实driver UNKNOWN。历史同型写法作为既有限制保留，独立总审应按批准范围判断，不静默关闭。

恢复用例是在真实PG上以已知提交边界注入合成异常，再用独立Session读回；不是任意杀进程、断真实数据库或验证第三方收费UNKNOWN。原文、attempt、父子指针、重复effect及generator调用断言按已有合同记录。

### D61与D70：尚未满足的实际执行条件

- D61的普通PostgreSQL集成回归尚未在本次新head实际执行；本地专项27项不能替代它。现有Backend CI的普通PG入口可在未来exact commit上补足，勿为本轮扩建本地普通PG启动平台或复用历史库。
- D70的B45／竞争11和Dialogue迁移/运行job必须针对未来exact C2 commit实际成功；本地B43／Dialogue47只证明mock门禁。当前HEAD仍为C1 seal `c8824b3...`，其旧CI不得冒充C2结果。
- 远程前必须完成精确候选/hunk审计、暂存、提交和推送的分别批准。当前没有新提交，故没有可检查的新C2 remote run；本轮不提前标记remote PASS。

## 5. Git与产品边界

本轮无Git写操作，暂存区保持空；16个历史删除、ad、ignored .env.test及AGENTS/C3/BM-01既有工作保持。三份入口文档为混合差异，未来候选仅纳入C2相关hunk，不能整份文档带入C3修改。外部临时脚本与运行目录不纳入项目提交。当前候选为49路径：实施36、文档13；三份混合文档仅选择6个C2差异块，12个既有C3差异块排除。外部精确候选清单和文档patch已准备，patch对当前index的只读应用检查通过，尚未暂存，仍待正式预提交审查。

原合同、独立初审/复审、失败与前次17／13、最新27／16报告均保留，不回写历史执行结论。当前状态继续为**NOT SEALED / DEVELOPMENT SNAPSHOT ONLY / NOT PRODUCTION READY**。真实Provider、费用能力、语音/STT/TTS、真实个人资料、日记/资料集/多来源、C3激活/C4/C6、生产及旧UNKNOWN限制不变。

下一步：本轮证据/文档差集与提交候选审计，再按批准进行精确暂存、commit和push；等待该exact commit的完整Backend／B／Dialogue／AI Service远程结果后，才讨论最终封板。
