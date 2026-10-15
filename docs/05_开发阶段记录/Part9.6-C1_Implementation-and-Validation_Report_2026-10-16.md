# Part 9.6-C1 — 实施与验收记录归档

## 归档元数据

- 归档日期：2026-10-16；本轮 Documentation Only，未重跑测试。
- 当前状态：**合成离线实施及定向复审通过，Git 闭环待完成**。
- 下方原实施报告属于修复前快照：183／330；其“待独立审查”和初次58项覆盖声明保留历史。随后独立初审发现三项P2及C52/C54缺口，不能将该快照当成最终封板结论。
- 初审历史见[独立实现审查](Part9.6-C1_Independent-Implementation-Review_Report_2026-10-16.md)；最新20／203／350及关闭意见见[修复与定向复审](Part9.6-C1_Remediation-and-Targeted-Review_Report_2026-10-16.md)；可移植的源码哈希、完整执行节点及最新C01–C58对账见[验收元数据](Part9.6-C1_Validation-Evidence_2026-10-16.json)。
- 原实施报告 SHA-256：`5853a74f92cc6e87081ca6e07232948b5e077ef58e359b1a9737e267b49d55a0`；原路径为仓库外实施证据目录内的 `Implementation-Report.md`。
- 下方文件/行号对应当时源码哈希，后续修复使部分行号变化；不按当前行号反向推定旧问题仍存在。原记录未被本轮重写为新的执行证明。

---

## 原实施报告（历史原文）

# Part 9.6-C1 — Synthetic Offline Implementation Report

## Result

PASS — implementation and synthetic offline validation. Formal independent implementation review remains next.

- Baseline: `master @ 3873c744eec87af2740731d1098cbd488d145ef2`; HEAD unchanged; index empty.
- Contract SHA-256: `f036874a1c8a3401c73a375bc2e833bd745fcaaebd0f97fadbea329c06a18563`.
- Exact scope: 11 new files (7 implementation, 4 tests); no existing project file modified.
- Real voice/STT/TTS, Provider/network, Backend/HTTP, PostgreSQL/Docker/migrations, real Consent and production: NOT RUN / NOT IMPLEMENTED by this increment.

## Validation

| Check | Actual result |
| --- | --- |
| C1 targeted synthetic tests | 183 passed / 0 skipped |
| Full AI Service suite | 330 passed / 0 skipped |
| Existing AI Service regression included above | 147 passed |
| Ruff | PASS |
| Format | PASS, all 25 app/tests files |
| Contract C01–C58 mapping | All 58 linked to code, test nodes and actual execution evidence |
| Local interpreter | Python 3.14.0; no dependencies installed or changed |

## Implementation

- Strict frozen DTOs, exact source quotes and fixed version selections; documents keep independent identity.
- Pure ordered reducer: overlapping speech/typing gates, explicit policy thresholds, one automatic silence reservation, pause/resume/end, cancellation/stop effects.
- Complete callback binding, deterministic IDs, receipt-based replay and question deduplication; late old results cannot revive tasks.
- Restricted source prechecks, immutable stable source-version metadata, clean-context rebuild checks; no real authorization or deletion execution.
- Explicit offline Stub injection and safe fixed failures; no default Provider or network fallback.

## Internal checks

Internal read-only spot checks found and closed restricted-body digest ordering, stable source-version aliasing, text-turn reuse and direct Context metadata gaps. Targeted regressions were added. This is not the separately required formal independent implementation review.

## Safety

- All 316 pre-existing protected nonsecret files match their preflight hashes.
- Existing AGENTS/C3/BM-01/mixed documentation changes retained unchanged.
- 16 historical deletions remain unstaged; `ad` remains untracked; `.env.test` remains ignored and unread.
- No documentation/config/workflow edits, Git staging/commit/push, database or Docker operation.

## Exact new files

| Path | SHA-256 |
| --- | --- |
| `services/ai-service/app/dialogue/__init__.py` | `f62b633dc3bdcfc168c37680166934c9fdc3e65f6d91a1ba3b4b8e2e18ba37eb` |
| `services/ai-service/app/dialogue/contracts.py` | `e4520f3d886dd36b96dbb6d9462d7820e50a9b81be5d2b388f57481d6d5619c4` |
| `services/ai-service/app/dialogue/context.py` | `cd50c9f45bc7fe6a2a7e5af38051b61cb4ed0a4b3506c29dccd4d7189f0187aa` |
| `services/ai-service/app/dialogue/controller.py` | `5967dbe4ce3d41cfa79e8acd15d8e41bf4d50bbc8f15060f88730432384f1a20` |
| `services/ai-service/app/dialogue/provider.py` | `e9b4f579412709965c805c4004d678940a12845bff4fe230b503cc7de51fa2f5` |
| `services/ai-service/app/dialogue/mock.py` | `55634aaff6d95f4cca2a78cf478e953f0bc435ffcdd2309d1b5d225eff042a2b` |
| `services/ai-service/app/dialogue/runner.py` | `4d28a192f9299552b607c4dbb2e41381743f786be08c1a0c6f5965ec165dc27f` |
| `services/ai-service/tests/test_dialogue_contracts.py` | `3de5acd221d5e2c525ea4f9a18834b881d5729af9d3bb2d5e715a57e39b7cf1f` |
| `services/ai-service/tests/test_dialogue_context.py` | `7e6505815c26953f9dba4903ba1033f497a780c8bc7cf57a13a49910d0128c58` |
| `services/ai-service/tests/test_dialogue_controller.py` | `8ffa841ad441f1c4c88149d7c59e6835223fd73124de3f1c998bab058ca46d15` |
| `services/ai-service/tests/test_dialogue_runner.py` | `371a431c751d64879bea654a1a6d7dfd4f3adbab5e3bb0eed911738d38f8bb95` |

## Evidence

- `targeted-final.xml`: final 183-node execution metadata; no captured passing-test logs.
- `full-final.xml`: final 330-node execution metadata.
- `acceptance-C01-C58.json`: all 58 acceptance IDs, exact code references and executed test nodes.
- `static-boundary-audit.json`: implementation import/call surface audit and its limits.
- `source-before.json` / `final-audit.json`: protected worktree hashes and integrity results.

## Next

READY FOR INDEPENDENT IMPLEMENTATION REVIEW. No stage, commit, push, real Provider or later phase has been authorized by this result.

## C01–C58 index

| ID | Executed test nodes | Code references |
| --- | --- | --- |
| C01 | `test_c01_c38_context_selection_rejects_duplicate_refs_directly`<br>`test_c01_constructed_invalid_nested_instance_is_revalidated`<br>`test_c01_event_envelope_rejects_bool_int_and_untyped_extra_payload`<br>`test_c01_extra_fields_rejected_at_scope_and_nested_source`<br>`test_c01_manifest_rejects_duplicate_refs`<br>`test_c01_policy_integer_limits_are_strict_positive`<br>`test_c01_policy_requires_all_parameters_and_ordered_pause_thresholds`<br>`test_c01_source_body_rejects_empty_or_oversize_without_rewriting`<br>`test_c01_source_version_rejects_bool_and_coercion` | `services/ai-service/app/dialogue/contracts.py:107`<br>`services/ai-service/app/dialogue/contracts.py:557`<br>`services/ai-service/app/dialogue/controller.py:16` |
| C02 | `test_c02_reducer_keeps_state_context_and_event_immutable`<br>`test_c02_sources_manifest_context_and_nested_scope_are_frozen` | `services/ai-service/app/dialogue/contracts.py:107`<br>`services/ai-service/app/dialogue/contracts.py:557`<br>`services/ai-service/app/dialogue/controller.py:16` |
| C03 | `test_c03_c50_selected_cross_scope_source_fails_closed`<br>`test_c03_scope_mismatch_rejects_without_any_generation` | `services/ai-service/app/dialogue/context.py:23`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/context.py:91`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C04 | `test_c04_start_light_listens_without_automatic_opening` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C05 | `test_c05_c06_c07_active_input_blocks_manual_and_automatic_output` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C06 | `test_c05_c06_c07_active_input_blocks_manual_and_automatic_output` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C07 | `test_c05_c06_c07_active_input_blocks_manual_and_automatic_output` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C08 | `test_c08_c09_complete_threshold_reserves_once_and_preserves_silence_origin` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C09 | `test_c08_c09_complete_threshold_reserves_once_and_preserves_silence_origin`<br>`test_c09_c31_valid_results_echo_every_reserved_binding` | `services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/controller.py:177`<br>`services/ai-service/app/dialogue/controller.py:159`<br>`services/ai-service/app/dialogue/context.py:71` |
| C10 | `test_c10_incomplete_and_unknown_use_longer_wait_and_neutral_outcomes`<br>`test_c10_stub_cannot_return_question_when_only_ack_or_no_reply_allowed` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C11 | `test_c11_ai_delivery_and_later_ticks_do_not_refill_automatic_allowance` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C12 | `test_c12_c13_text_commit_cannot_reuse_an_existing_human_turn_id`<br>`test_c12_c52_speech_start_end_and_final_commit_share_one_cycle` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C13 | `test_c12_c13_text_commit_cannot_reuse_an_existing_human_turn_id`<br>`test_c13_typing_end_does_not_create_turn_or_refill_cycle` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C14 | `test_c14_c15_c45_no_reply_or_failure_cannot_automatically_retry` | `services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/controller.py:177`<br>`services/ai-service/app/dialogue/controller.py:159`<br>`services/ai-service/app/dialogue/context.py:71` |
| C15 | `test_c14_c15_c45_no_reply_or_failure_cannot_automatically_retry`<br>`test_c15_cancelled_generation_keeps_silence_allowance_consumed` | `services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/controller.py:177`<br>`services/ai-service/app/dialogue/controller.py:159`<br>`services/ai-service/app/dialogue/context.py:71` |
| C16 | `test_c16_manual_requests_work_without_source_and_do_not_manufacture_answers` | `services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/controller.py:177`<br>`services/ai-service/app/dialogue/controller.py:159`<br>`services/ai-service/app/dialogue/context.py:71` |
| C17 | `test_c17_replay_returns_metadata_without_reexecuting_stub_or_effect` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C18 | `test_c18_same_event_id_with_changed_payload_rejected_without_body` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C19 | `test_c19_sequence_or_time_regression_blocks_and_cancels` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C20 | `test_c20_stale_version_cannot_reserve_another_generation` | `services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/controller.py:177`<br>`services/ai-service/app/dialogue/controller.py:159`<br>`services/ai-service/app/dialogue/context.py:71` |
| C21 | `test_c21_record_only_accepts_input_but_never_generates_or_delivers` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C22 | `test_c22_pause_before_reservation_does_not_auto_generate_on_resume`<br>`test_c22_pause_stops_playback_resume_does_not_republish` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C23 | `test_c23_end_is_terminal_with_replay_metadata_only` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C24 | `test_c24_generating_interruption_advances_epoch_and_ignores_old_result` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C25 | `test_c25_ready_typing_discards_output_without_claiming_delivery` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C26 | `test_c26_c30_c55_delivery_interrupt_marks_started_not_delivered_and_stops` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C27 | `test_c27_delivery_receipt_requires_complete_binding`<br>`test_c27_ready_callback_requires_each_original_reservation_field`<br>`test_c27_response_binding_rejects_each_mismatched_field` | `services/ai-service/app/dialogue/controller.py:278`<br>`services/ai-service/app/dialogue/controller.py:426`<br>`services/ai-service/app/dialogue/runner.py:172`<br>`services/ai-service/app/dialogue/runner.py:99` |
| C28 | `test_c28_c54_late_callbacks_after_stop_cannot_revive_old_output` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C29 | `test_c29_c30_c55_delivered_or_interrupted_questions_are_not_automatically_repeated` | `services/ai-service/app/dialogue/controller.py:331`<br>`services/ai-service/app/dialogue/controller.py:426`<br>`services/ai-service/app/dialogue/controller.py:73`<br>`services/ai-service/app/dialogue/contracts.py:99` |
| C30 | `test_c26_c30_c55_delivery_interrupt_marks_started_not_delivered_and_stops`<br>`test_c29_c30_c55_delivered_or_interrupted_questions_are_not_automatically_repeated` | `services/ai-service/app/dialogue/controller.py:331`<br>`services/ai-service/app/dialogue/controller.py:426`<br>`services/ai-service/app/dialogue/controller.py:73`<br>`services/ai-service/app/dialogue/contracts.py:99` |
| C31 | `test_c09_c31_valid_results_echo_every_reserved_binding`<br>`test_c31_ack_rejects_emotion_or_biography_assertion`<br>`test_c31_question_cannot_invent_neutral_biographical_claims` | `services/ai-service/app/dialogue/contracts.py:324`<br>`services/ai-service/app/dialogue/runner.py:99`<br>`services/ai-service/app/dialogue/context.py:44`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C32 | `test_c32_assistant_history_and_summary_are_not_independent_fact_sources`<br>`test_c32_c35_summary_or_assistant_text_cannot_replace_original_quote` | `services/ai-service/app/dialogue/contracts.py:324`<br>`services/ai-service/app/dialogue/runner.py:99`<br>`services/ai-service/app/dialogue/context.py:44`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C33 | `test_c33_sourced_question_preserves_exact_uncertain_negative_source`<br>`test_c33_uncertainty_negation_and_contradiction_remain_exact_quotes` | `services/ai-service/app/dialogue/contracts.py:324`<br>`services/ai-service/app/dialogue/runner.py:99`<br>`services/ai-service/app/dialogue/context.py:44`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C34 | `test_c34_c35_runner_rechecks_semantic_context_before_invoking_stub`<br>`test_c34_conflicting_history_sequence_is_rejected`<br>`test_c34_history_uses_sequence_and_window_keeps_older_quote_dependency` | `services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/context.py:91`<br>`services/ai-service/app/dialogue/runner.py:38` |
| C35 | `test_c32_c35_summary_or_assistant_text_cannot_replace_original_quote`<br>`test_c34_c35_runner_rechecks_semantic_context_before_invoking_stub`<br>`test_c35_c39_c57_stable_version_identity_cannot_alias_new_metadata`<br>`test_c35_c58_known_source_cannot_change_body_even_with_fresh_matching_fingerprint`<br>`test_c35_quote_offsets_and_text_must_all_match`<br>`test_c35_same_ref_changed_body_cannot_pass_original_fingerprint` | `services/ai-service/app/dialogue/contracts.py:324`<br>`services/ai-service/app/dialogue/runner.py:99`<br>`services/ai-service/app/dialogue/context.py:44`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C36 | `test_c36_c56_capacity_blocks_without_eviction_but_end_has_reserved_receipt`<br>`test_c36_context_limits_do_not_silently_drop_dependencies` | `services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/controller.py:177`<br>`services/ai-service/app/dialogue/controller.py:159`<br>`services/ai-service/app/dialogue/context.py:71` |
| C37 | `test_c37_unselected_diary_and_older_session_never_enter_context` | `services/ai-service/app/dialogue/context.py:23`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/context.py:91`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C38 | `test_c01_c38_context_selection_rejects_duplicate_refs_directly`<br>`test_c38_manifest_pins_version_even_when_catalog_contains_new_versions_and_members` | `services/ai-service/app/dialogue/context.py:23`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/context.py:91`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C39 | `test_c35_c39_c57_stable_version_identity_cannot_alias_new_metadata`<br>`test_c39_replace_selection_cancels_old_binding_and_requires_new_manifest_version` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C40 | `test_c40_c56_restricted_old_context_is_not_hashed_for_request_or_safety_stop`<br>`test_c40_c57_restriction_blocks_old_context_until_rebuilt_without_dependencies`<br>`test_c40_runner_rejects_restricted_source_without_calling_provider` | `services/ai-service/app/dialogue/controller.py:192`<br>`services/ai-service/app/dialogue/controller.py:211`<br>`services/ai-service/app/dialogue/controller.py:218`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C41 | `test_c41_skipped_topic_remains_suppressed_until_explicit_unskip` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C42 | `test_c42_c50_document_origin_does_not_allow_half_filled_fake_session_scope`<br>`test_c42_c50_document_preserves_independent_id_without_fake_session_or_message` | `services/ai-service/app/dialogue/contracts.py:128`<br>`services/ai-service/app/dialogue/contracts.py:142`<br>`services/ai-service/app/dialogue/context.py:133` |
| C43 | `test_c43_callback_rejects_foreign_scope_and_bool_time`<br>`test_c43_explicit_stub_is_called_once_and_runner_does_not_own_state`<br>`test_c43_no_provider_returns_fixed_refusal_without_fallback` | `services/ai-service/app/dialogue/runner.py:142`<br>`services/ai-service/app/dialogue/runner.py:99`<br>`services/ai-service/app/dialogue/mock.py:16` |
| C44 | `test_c44_context_builder_performs_no_file_environment_or_clock_reads`<br>`test_c44_reducer_does_not_call_io_clock_randomness_or_provider` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/runner.py:172` |
| C45 | `test_c14_c15_c45_no_reply_or_failure_cannot_automatically_retry`<br>`test_c45_exception_is_not_logged_printed_or_copied_and_no_retry_occurs`<br>`test_c45_malformed_provider_shape_is_fixed_invalid_response` | `services/ai-service/app/dialogue/runner.py:142`<br>`services/ai-service/app/dialogue/runner.py:99`<br>`services/ai-service/app/dialogue/mock.py:16` |
| C46 | `test_c46_effect_identity_is_deterministic_from_reserved_event`<br>`test_c46_synthetic_fixture_generation_is_repeatable` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:348`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/runner.py:172` |
| C47 | 147 existing regression nodes | `services/ai-service/app/contracts.py`<br>`services/ai-service/app/interview_agent.py`<br>`services/ai-service/app/memory_extraction.py` |
| C48 | `test_c48_import_surface_has_no_backend_db_network_sdk_or_configuration_module` | `services/ai-service/app/dialogue/__init__.py`<br>`services/ai-service/app/dialogue/contracts.py`<br>`services/ai-service/app/dialogue/context.py`<br>`services/ai-service/app/dialogue/controller.py`<br>`services/ai-service/app/dialogue/provider.py`<br>`services/ai-service/app/dialogue/mock.py`<br>`services/ai-service/app/dialogue/runner.py` |
| C49 | `test_c49_selected_old_session_keeps_its_original_scope` | `services/ai-service/app/dialogue/context.py:23`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/context.py:91`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C50 | `test_c03_c50_selected_cross_scope_source_fails_closed`<br>`test_c42_c50_document_origin_does_not_allow_half_filled_fake_session_scope`<br>`test_c42_c50_document_preserves_independent_id_without_fake_session_or_message` | `services/ai-service/app/dialogue/context.py:23`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/context.py:91`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C51 | `test_c51_extraction_manifest_is_not_dialogue_permission`<br>`test_c51_policy_cannot_hot_swap_even_with_unchanged_version` | `services/ai-service/app/dialogue/context.py:23`<br>`services/ai-service/app/dialogue/context.py:133`<br>`services/ai-service/app/dialogue/context.py:91`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C52 | `test_c12_c52_speech_start_end_and_final_commit_share_one_cycle`<br>`test_c52_late_complete_commit_for_a_does_not_overwrite_current_incomplete_b` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C53 | `test_c53_callback_accepts_reserved_version_after_legal_intermediate_tick`<br>`test_c53_callback_uses_current_envelope_and_preserves_reservation_binding` | `services/ai-service/app/dialogue/controller.py:278`<br>`services/ai-service/app/dialogue/controller.py:426`<br>`services/ai-service/app/dialogue/runner.py:172`<br>`services/ai-service/app/dialogue/runner.py:99` |
| C54 | `test_c28_c54_late_callbacks_after_stop_cannot_revive_old_output`<br>`test_c54_old_bound_callbacks_do_not_block_or_complete_new_request` | `services/ai-service/app/dialogue/controller.py:278`<br>`services/ai-service/app/dialogue/controller.py:426`<br>`services/ai-service/app/dialogue/runner.py:172`<br>`services/ai-service/app/dialogue/runner.py:99` |
| C55 | `test_c26_c30_c55_delivery_interrupt_marks_started_not_delivered_and_stops`<br>`test_c29_c30_c55_delivered_or_interrupted_questions_are_not_automatically_repeated`<br>`test_c55_normalization_is_nfkc_casefold_and_removes_whitespace_and_punctuation` | `services/ai-service/app/dialogue/controller.py:331`<br>`services/ai-service/app/dialogue/controller.py:426`<br>`services/ai-service/app/dialogue/controller.py:73`<br>`services/ai-service/app/dialogue/contracts.py:99` |
| C56 | `test_c36_c56_capacity_blocks_without_eviction_but_end_has_reserved_receipt`<br>`test_c40_c56_restricted_old_context_is_not_hashed_for_request_or_safety_stop`<br>`test_c56_safe_stops_override_only_stale_optimistic_version`<br>`test_c56_source_restriction_also_overrides_stale_version_and_cancels` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
| C57 | `test_c35_c39_c57_stable_version_identity_cannot_alias_new_metadata`<br>`test_c40_c57_restriction_blocks_old_context_until_rebuilt_without_dependencies`<br>`test_c57_rebuilt_context_must_remove_old_ai_work_depending_on_restricted_source` | `services/ai-service/app/dialogue/controller.py:192`<br>`services/ai-service/app/dialogue/controller.py:211`<br>`services/ai-service/app/dialogue/controller.py:218`<br>`services/ai-service/app/dialogue/controller.py:518` |
| C58 | `test_c35_c58_known_source_cannot_change_body_even_with_fresh_matching_fingerprint`<br>`test_c58_commit_context_requires_exact_next_revision_and_actual_current_source`<br>`test_c58_ordinary_event_cannot_smuggle_a_different_context` | `services/ai-service/app/dialogue/controller.py:518`<br>`services/ai-service/app/dialogue/controller.py:395`<br>`services/ai-service/app/dialogue/controller.py:218` |
