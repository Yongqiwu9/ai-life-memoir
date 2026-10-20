# Session 合成文字接入 — Contract Addendum V0.4

Baseline: master c8824b3c2c1d7c9ae6d633461787431166cd7a07. Date 2026-10-16.
Status REVISED DRAFT FOR TARGETED INDEPENDENT RE-REVIEW. C2 is a provisional package name.
External design artifact only. No repository modifications, tests, HTTP, database, Docker, Git writes or secret reads authorized. User scope A: fresh current Session synthetic text only. Real people/provider/voice/documents/collections/C3 activation/C4/C6/production/old UNKNOWN remain excluded. Original eleven C1 paths preserved.

## 1. Authority, protocol and transaction clarification

- Backend owns JWT, current Owner scope, server-injected exact synthetic account/Session/source allocation, database and processing gates. AI Service owns C1 initialize/transition and explicit offline generation. No cross-app app import or copied reducer.
- Independent authenticated POST endpoints: /internal/v1/dialogue/initialize, /transitions, /generations. Transition is pure and never dispatches effects. Generation uses explicit Stub injection only. Default transport and allocation gates unavailable; client synthetic/available/consent/provider fields cannot grant access.
- Strict wire DTOs bind profile `session-text-dialogue.synthetic.v1`, kernel `reminiscence-dialogue.synthetic.v1`, actor/Family/Member/Interview/Session, request/effect IDs, input digest, persistence version, core version/epoch, stop fence, Context ID/revision, Policy version and generation reservation. Authenticate AND validate response bindings. Required actual transport deadlines, body limits and endpoint allowlist; test factory injects ephemeral credentials. No production provider or secret reader.
- V0.1 transaction clarification: original Message + source binding + durable input Turn commit atomically. Core application is a second transaction. AI Service outage must not lose an accepted original or falsely claim its core event applied. 202 includes saved Message ID and queued command. This replaces the earlier ambiguous all-or-nothing source-plus-AI wording; it requires user approval before implementation.
- Normal application: prepare fixed input, release all transactions/locks, call AI Service, reacquire Session->State->Turn/Effect locks, recheck permission, sources/fingerprints, Context/Policy and CAS/fence before commit. No service/network call while holding a database transaction. No partial proposal publication, auto expected-version rewrite or implicit source reselection.
- Backend persistence_version is the API expected_version; C1 version/epoch are separate counters. command_order is monotonic under parent lock; discarded commands may leave gaps. Core applied seq is contiguous last_seq+1 only on application. A normal reservation can be superseded by a safety fence. Only one preparing normal transition per Session.
- POST commands/{id}/apply explicitly applies known queued/pure-transition-retry commands in order. GET and ordinary replay never call it. No scheduler/broker/general worker platform. Generate effects claim durably before a separate call; claimed/unknown effects never redispatch after crash. Output-unknown blocks Session until end/new Session, including requests with new keys.

## 2. Checkpoint field-by-field partition

One current checkpoint per existing State, no retained sensitive versions. Physically separate metadata_json and sensitive_json; metadata SELECTs defer sensitive_json. Complete C1 State is validated before split and after merge, without copying decision logic.

metadata_json stores these exact DialogueState fields:
- scope, contract_version, policy, status, mode, version, epoch, last_seq, last_time_ms;
- speaking, typing, active_speech_turn_id, current_human_turn_id, turn_cycles;
- committed_refs, restricted_refs, silence_cycle, cycle_consumed, auto_suspended, silence_since_ms, semantic_hint;
- context_id, context_revision, context_digest, context_source_refs, selection_refs, known_source_revisions;
- skipped_keys, manifest_id, manifest_version, pending_effect, known_requests, event_receipts, terminal_receipt;
- question_receipts except normalized_text;
- ready_response/active_response except text and basis_quotes[].text. All binding fields and quote ref/start/end remain metadata.

sensitive_json stores exactly the removed leaves keyed by stable response/receipt IDs: question_receipts[].normalized_text; ready_response.text OR active_response.text; corresponding basis_quotes[].text. Missing, extra or orphan leaves reject merge. Slot exclusivity follows C1. This is sensitive derived content, not pure metadata; ready/active body can temporarily coexist with Message while delivering and is tracked as a copy. Client topic/key values must be existing server-issued opaque identifiers, not free text.

Reconstruction:
1. Select envelope/checkpoint header/metadata, context manifest and ALL dependency rows before any sensitive/body access. Match current Owner/allocation/Session/profile, versions/epoch/fence and Context/Policy.
2. Validate direct and transitive AI-history dependencies. Missing/restricted/unknown source: no sensitive/body SELECT; fence, checkpoint unavailable, blind-clear sensitive_json, revoke tickets/effects. No restore in this increment; only end/new Session.
3. After authorization, load only pinned Message IDs, verify immutable fingerprints and rebuild Context. Never select latest on replay.
4. Context records store ordered full source refs/fingerprints and history sequence/ref/role/frozen delivery/response_id, ordered SummaryEntry label/ref/start/end, explicitly empty external-selection manifest with versioned snapshot identity and asked/skipped keys. Rebuild exact text and quotes from permitted original/output Messages; compare C1 canonical digest and ID. No body snapshot, silent dropped dependency or fabricated substitute.
5. Merge leaves into State, validate through AI Service C1 DTO, verify returned wire/header consistency, CAS persist. New checkpoint replaces old; no event/Turn/provider raw packet copy.
6. Returned state removes completed/discarded draft leaves. End/source failure blind-clears sensitive column. This clears ephemeral checkpoint copies, not original deletion or C6 completion. Original and assistant Message bodies retain policy restrictions and affected list/read APIs deny access.
7. Future C6 inventory includes every sensitive checkpoint leaf and output/history copy; no retention days or restoration rights invented.

Source projection: only trusted fresh current-Session user/text Message qualifies. entity_id=version_id=actual immutable Message ID, version=1, origin=user_text. This explicitly represents one immutable Message, not a fabricated document version or Artifact. No old Message enrollment. Changed bytes/role/source/scope or missing Message fail closed. C1 bindings do not replace C3 global provenance.

## 3. Safety fence and synchronization state machine

Existing State row remains authoritative. Its status is effective Backend state; checkpoint records the last applied C1 state/version. During sync_required those may differ explicitly; expose checkpoint_sync, never fake a C1 version advance. All generation/delivery denied until valid.

New safety command (pause, typing_started, record_only, end, trusted restriction): authenticate current Owner; read metadata only; lock Session then State; check idempotency; advance fence and persistence_version once; discard superseded reservations and revoke delivery effects/tickets; persist body-free control Turn. Source processing permission is not required for content-free stop. Recheck fence under lock before every later publication.

| Condition | Effective state / Session | Checkpoint | Required behavior |
|---|---|---|---|
| Normal initialized | C1 state / active | valid | normal commands |
| Pause accepted, service pending/down | paused / active | sync_required | 202 fenced; save text with queued input; no generation/delivery |
| Pause applied | paused / active | valid | completed metadata, no output |
| Typing-start fenced | prior state plus input fence / active | sync_required | no generation/delivery until applied |
| record_only pending | effective record_only / active | sync_required | no generation, inputs durable |
| Resume with pending controls/input | paused / active | sync_required | apply safety/input in original order, reject generate/deliver effects in sync phase; stay fenced on failure |
| Resume applied | listening / active | valid | no old output/refill/automatic question |
| End from any non-ended state | ended / completed, ended_at UTC | unavailable | completed terminal command; blind-clear leaves; no RPC needed |
| Same stop key replay | unchanged | unchanged | no new fence/version/effect |
| Another pause already fenced | paused / active | unchanged | already-paused metadata, no second core pause |
| End supersedes pending work | ended / completed | unavailable | discard controls/input application/effects; never drain after end |
| Missing/restricted source or damaged checkpoint | blocked / active | unavailable | fence, revoke, blind-clear; only end allowed |
| Pure transition failure | prior effective state (fenced if safety) | sync_required | queued retryable command, no applied seq; explicit apply only |
| Generation outcome unknown | blocked / active | unavailable | no redispatch/new-key escape; end/new Session |

End is Backend Session terminalization; do not pretend a C1 end response was received. Archived checkpoint is unavailable forever, never hydrated; metadata can remain at its historical core status/version. Nonterminal stops must pass the same C1 reducer before resume. Timer/manual-generation commands superseded by stop are discarded. Paused Message save and durable event remain atomic, not a claim that C1 already consumed them.
Replay synchronization is explicit (resume/apply), never GET; apply only non-generative queued safety/typing/input events in original order. Unexpected generation/delivery effects fail closed. Generation claim/retry rules are independent.
Server logical event time = persisted clock origin plus nondecreasing trusted elapsed; clamp regression, block uncertain synthetic timer dispatch; never trust client timestamps. No background production timer. Late result requires full original binding, current epoch/fence, active slot and dependency closure; old callbacks yield ignored/discarded metadata, never touch a newer response.

## 4. Table specifications

Types: UUID, BIGINT, INT, VARCHAR(n), BYTEA, JSON with PostgreSQL JSONB variant, TIMESTAMPTZ. New tables all created_at/updated_at NOT NULL UTC server timestamps. Immutable fields cannot change via Service; no claim that nested JSON immutability is DB-enforced. Every CHECK branch uses explicit NULL rules. Nested DTO/write-once/privacy rules are Schema/Service protections with tests.

### Existing interview_agent_states additions (nullable for legacy)

integration_profile VARCHAR64; persistence_version BIGINT; stop_fence BIGINT; last_applied_event_seq BIGINT; next_command_order BIGINT; active_command_id UUID NULL; checkpoint_status VARCHAR24; effective_mode VARCHAR16; current_context_revision BIGINT; clock_origin_at TIMESTAMPTZ.
New profile requires all control fields except active_command_id (nullable throughout) and current_context_revision only during initialization; initialized requires context pointer. Legacy profile NULL requires new fields NULL. Counters>=0, next order>0; mode light/record_only; sync valid/sync_required/unavailable. Existing status/version/generation_epoch retained, explicit new profile status branch. Ended=>unavailable and Session completed (cross-table Service rule under lock).
Existing Session PK/FK CASCADE unchanged. INDEX(profile,status). Deferred NO ACTION composite FK(session_id,current_context_revision)->contexts(session_id,revision), added after contexts. Valid status/core-version/epoch equality checked at Service publication.

### Existing interview_agent_turns additions (nullable for legacy)

integration_profile VARCHAR64; command_order BIGINT; event_id UUID; event_kind VARCHAR40; command_payload JSON body-free allowlist; reserved_event_seq BIGINT; applied_event_seq BIGINT; reserved_persistence_version BIGINT; reserved_stop_fence BIGINT; fingerprint_key_id VARCHAR100; result_metadata JSON body-free.
Existing id/session/actor/key/fingerprint/timestamps kept. Actor FK RESTRICT, Session CASCADE. UNIQUE(session_id,id), UNIQUE(session_id,event_id), UNIQUE(session_id,command_order), partial UNIQUE(session_id,applied_event_seq) WHERE not NULL; existing session/key uniqueness retained. New preparing partial unique one per Session. Old pending unique narrowed to legacy profile NULL, old semantics unchanged.
New states queued/preparing/completed/failed/discarded. queued: immutable payload/order, no success/applied seq. preparing: reservation versions, no success. completed: safe result+finished_at; applied seq optional for Backend terminal end. failed/discarded: safe code+finished_at, no successful output. New profile/contract branch required; all old checks gated explicitly by profile NULL, not merely widening ck_agent_contract.
Storage/API contract_version and result_state_contract_version use short literal interview-agent.v3 (18 chars); integration_profile uses session-text-dialogue.synthetic.v1 (34 chars) only in VARCHAR64. State and Turn legacy String32 columns need no widening. Core contract remains checkpoint-specific. HMAC request fingerprint + key ID; no configured provider/key=unavailable, unknown old key cannot bypass verification. C1 event digests are structural and not an authorization proof.

### interview_agent_checkpoints

session_id UUID PK/FK State CASCADE; checkpoint_version BIGINT NN; core_version BIGINT NN; core_epoch BIGINT NN; last_seq BIGINT NN; context_revision BIGINT NN; format_version VARCHAR64 NN; metadata_json JSON NN; sensitive_json JSON NULL; metadata_digest VARCHAR64 NN; content_status VARCHAR16 NN live/quarantined/purged; timestamps NN.
Deferred NO ACTION FK(session,context_revision)->contexts. Counters>=0, context revision>0; quarantined/purged requires sensitive_json NULL. Current row only, CAS replace. Purged/quarantined never becomes live here. No client update API.

### interview_agent_sources

session_id UUID NN FK State CASCADE; stable_message_id UUID NN; live_message_id UUID NULL FK Messages.id SET NULL; message_sequence BIGINT NN; origin VARCHAR16 NN user_text; source_role VARCHAR16 NN user; version_ordinal INT NN=1; fingerprint VARCHAR64 NN; availability VARCHAR16 NN available/restricted/missing; timestamps NN.
PK(session,stable_message_id), UNIQUE(session,message_sequence). CHECK live ID NULL OR equals stable ID. Identity/sequence/fingerprint write-once; availability only available->restricted/missing. NULL live FK always unavailable even if availability field stale. No restore. Composite SET NULL including session_id is forbidden (would null scope); single FK does not independently enforce same-session source, which is explicit Service/allocation protection. Add UNIQUE(session_id,id) to existing Messages for scoped references below.

### interview_agent_contexts (append-only metadata)

session_id UUID NN FK State CASCADE; revision BIGINT NN; context_id UUID NN; manifest_id UUID NN; manifest_version BIGINT NN>=1; purpose VARCHAR16 NN dialogue; context_digest VARCHAR64 NN; source_order/history_order/quote_slices/asked_keys/skipped_keys JSON NN; timestamps NN.
PK(session,revision), UNIQUE(context_id), UNIQUE(session,context_id); revision>0; no external selections or documents. source_order stores full immutable SourceVersionRef and fingerprint. history_order stores frozen sequence/ref/role/delivery/response_id; quote_slices stores frozen ordered label/ref/start/end; label and delivery are exact C1 enums. JSON has no body/quote text. Later delivery status changes cannot rewrite an older context revision. Assistant history IDs bind actual server response/effect/output Message. All immutable; runtime permission still rechecked. Capacity overflow blocks, no silent loss of dependencies, end remains available.

### interview_agent_effects

id UUID PK = C1 effect ID; session_id UUID NN FK State CASCADE; origin_turn_id UUID NN; request_id UUID NN; kind VARCHAR24 NN generate/deliver/cancel_generation/stop_playback; epoch/stop_fence/context_revision BIGINT NN; status VARCHAR24 NN reserved/claimed/ready/published/completed/failed/discarded/unknown; binding_json JSON NN body-free; response_id UUID NULL; output_message_id UUID NULL FK Messages.id SET NULL; output_stable_id UUID NULL; token_digest BYTEA NULL; claimed_at/finished_at TIMESTAMPTZ NULL; timestamps NN.
UNIQUE(session,id); composite FK(session,origin_turn_id)->Turns(session,id) CASCADE; FK(session,context_revision)->contexts deferred NO ACTION. Partial UNIQUE(response_id) WHERE kind=generate and response_id not NULL; deliver may share response. UNIQUE(output_stable_id) WHERE non-null; only deliver owns output IDs, generate doesn't duplicate it. CHECK live output NULL OR equals stable. token digest NULL OR length32. Terminal status requires finished_at. Partial busy-generate uniqueness per Session for reserved/claimed/ready; no safety effect affected. Service validates actual output same Session before body use (single live FK is not such a DB guarantee).
Claim durable before generate. Claimed crash never redispatches; unknown terminal blocks Session; late result ignored. Ready checkpoint + effect result atomic. Delivery start creates output Message and C1 started transition atomically, later completion separate; missing output after deletion cannot regenerate.

### interview_agent_dependencies

id UUID PK; session_id UUID NN FK State CASCADE; source_message_id UUID NN; owner_kind VARCHAR16 NN context/checkpoint/effect; context_revision BIGINT NULL; effect_id UUID NULL; checkpoint_session_id UUID NULL; timestamps NN.
Composite FK(session,source)->Sources(session,stable) deferred NO ACTION. FK(session,context_revision)->Contexts CASCADE; FK(session,effect_id)->Effects CASCADE; checkpoint_session_id single FK Checkpoints.session CASCADE with CHECK equals session if non-null. Exact-one owner CHECK with explicit NULL branches. Partial unique per owner/source; INDEX(session,source,owner_kind). Direct+inherited AI dependencies included; edges never grant extra source reads. Context/effect edges append-only; checkpoint edges atomically replace with current row.
Future C6 includes checkpoint leaves, context dependencies, output copies and effects. CASCADE/SET NULL alone are not reported as deletion propagation. Legacy parent-delete behavior remains; missing parent during late job fails Owner resolution with no row resurrection.

## 5. HTTP contract completion

Prefix /api/v1/sessions/{s}/dialogue. JWT/current Owner and trusted allocation required for processing. Safe stopping authenticates Owner but doesn't require processing/body gate.
- GET /state: metadata only effective_status/persistence_version/core_version/epoch/fence/checkpoint_sync/queued refs, no hydration even for damaged checkpoint.
- POST /commands: key + expected_version + allowlisted action; no State/Context/time/provider/internal callback. 201 applied, 202 durably queued/fenced, 409 conflict, 503 unavailable/unknown.
- POST /messages: content + human_turn_id + key/expected_version. Message<=existing10000 limit, no truncation; context capacity may stop processing while preserving original. Atomic Message/binding/queued Turn; 201 applied, 202 saved+queued.
- POST /commands/{id}/apply: exact actor/Session command; queued/pure-transition retry only; stable payload/context; no leapfrogging input or redispatch claimed/unknown effects. GET /commands/{id}: same actor only, read-only metadata, missing/ambiguous=unknown, never permission to retry or enumerate other actors.
- POST /deliveries/{response}/start: key + version + server-issued token binding actor/session/response/effect/fence and required Policy expiry. Before body: scope/source/fence/epoch/slot recheck. Atomic assistant Message + C1 delivery_started + effect. Lost HTTP reply => started, not completed; replay no second Message.
- POST /deliveries/{response}/complete: same bound receipt; no user-meaning/voice claims, old token can't complete new response. Replays cannot re-expose restricted/ended text.
- Old generic Message/transcript writes deny DIALOGUE_WRITE_REQUIRED for new profile, preserving old resources. Existing message-list service checks new profile allocation/dependency availability before body SELECT, otherwise SOURCE_UNAVAILABLE. Source restriction only a trusted synthetic service method, no public Consent/withdrawal API.
- Protect parse/dependency/endpoint/serialization errors and logs in DEBUG both modes. Never echo SQL/DTO/credentials/body. GET/replay may not commit, begin a command, apply transition or call generation. HMAC missing/unknown key fails closed.

## 6. Revised exact candidate: 35 paths

22 NEW:
apps/backend/app/schemas/dialogue.py
apps/backend/app/models/dialogue_runtime.py
apps/backend/app/crud/dialogue.py
apps/backend/app/services/dialogue.py
apps/backend/app/services/dialogue_checkpoint.py
apps/backend/app/services/dialogue_client.py
apps/backend/app/services/dialogue_policy.py
apps/backend/app/api/v1/dialogue.py
apps/backend/app/core/dialogue_http.py
apps/backend/tests/test_dialogue_contracts.py
apps/backend/tests/test_dialogue.py
apps/backend/tests/test_dialogue_api.py
apps/backend/tests/integration/test_dialogue.py
apps/backend/tests/integration/test_dialogue_migration.py
apps/backend/alembic/versions/c296a4e8d102_session_text_dialogue.py
services/ai-service/app/dialogue/wire.py
services/ai-service/app/dialogue/service.py
services/ai-service/app/dialogue/http.py
services/ai-service/tests/test_dialogue_wire.py
services/ai-service/tests/test_dialogue_http.py
scripts/ci/run_dialogue_postgres.py
.github/workflows/dialogue-ci.yml

13 MODIFY:
scripts/ci/run_memory_workflow_postgres.py
apps/backend/tests/integration/test_memory_workflow.py
apps/backend/app/models/interview_agent.py
apps/backend/app/models/interview_message.py
apps/backend/app/schemas/interview_agent.py
apps/backend/app/crud/interview_agent.py
apps/backend/app/services/interview_agent.py
apps/backend/app/services/interview_message.py
apps/backend/app/database/models_import.py
apps/backend/app/main.py
apps/backend/pyproject.toml
services/ai-service/pyproject.toml
.github/workflows/backend-ci.yml

Message Model added for composite unique; B CI head maintenance adds two paths. V0.1 count32 -> V0.2 count33 -> V0.3 count35; requires approval. No original11 C1 files or AGENTS/C3/BM-01/16 historical deletions/ad/env. B script/test have only the explicitly limited project-head maintenance below. Docs separate. No implementation implied.

## 7. Migration and CI ownership

Single append c296a4e8d102 -> b196f0d47a21 (current source head). Nullable State/Turn fields first; Message/Turn unique keys before dependents; contexts before State/context pointer FK; checkpoint/effects/dependencies after respective parents; version-aware CHECK/index replacement last. No historical synthetic/authorization/source backfill. Preserve existing values, IDs/body hashes; new fields NULL on old rows. Head/current/check all required on actual authorized16.15.
Downgrade must reject ANY new profile row/new-field marker or row in ANY of five new tables. No business deletion to permit downgrade. Empty new tables and old fields NULL: reverse dependencies, restore exact old checks/indexes then remove columns. Verify fresh/legacy upgrade and each refusal branch.
B script explicitly hardcodes B_FILE/45 nodes/11 competition cases. Do NOT import its Manager, parameterize B_FILE/node lists, weaken isolation or convert it to a generic framework. Explicitly permit only project-head/parent bindings and source-manifest maintenance described in section10; B test head check changes to the same exact new head without allowing arbitrary environment-selected revisions. New narrow dialogue script may use reviewed algorithm as source reference only, with its own exact allowlist and independent review. Do not depend on uncommitted C3/BM-01 infrastructure. Manager performs migration and migration fixtures; restricted Runner performs runtime tests, never gains migration/provision/cleanup privileges.
New workflow: AI Service job runs full suite including original C1; PG16.15 job owns dialogue runtime/migration validation. Existing Backend integration excludes both new integration files; specialized job must own both, no missing-marker skip. Actual implemented node manifest determined/reviewed before execution, no invented success count. Current350 remains historical local evidence, not a hardcoded future total.
Manager requires verified unique DB/owner/restricted Runner allocation, negative cross-DB/role probes, migrations, actual allocation metadata, zero skips incl every competition node, confirmed process/connection exit, exact cleanup and absence proof. UNKNOWN=>retain/failing CI with sanitized evidence. No local DB/Docker/HBA action without separate task authorization.

## 8. Base acceptance D01-D64 (supplemented to D01-D73 in section10, all NOT RUN)

D01 strict wire/types/size; D02 every binding mismatch/cross-scope; D03 auth/config unavailable; D04 transition never calls generator; D05 same C1 initialize/transition immutable equivalence; D06 internal errors sanitized.
D07 Owner/Family/Session isolation; D08 forged synthetic/consent/provider denied; D09 fresh allocated Session only; D10 old v1/v2 preserved and new-profile old endpoint rejection.
D11 ALL State fields/leaves split-merge; D12 missing/orphan/extra leaves reject; D13 SQL instrumentation proves dependency checks before sensitive/body SELECT; D14 restart reconstructs exact Context order/digest, including nonempty summary labels and historical started before later delivered/interrupted; D15 missing/changed source blocks pre-provider; D16 transitive AI history restricted; D17 replace removes retired leaves/no raw context copy; D18 blind purge without sensitive SELECT; D19 GET metadata with corrupt checkpoint; D20 actual Message single-version projection/no fakeArtifact.
D21 original+binding+queuedTurn atomic; D22 rollback each input-write boundary; D23 outage saved+queued semantics; D24 apply once/no duplicate original; D25 generic text/transcript bypass denied; D26 concurrent Message parent lock/sequence; D27 same-key parallel oneMessage/Turn; D28 payload conflict/HMAC key rotation rules.
D29 stop fence durable before RPC; D30 outage pause+explicit sync; D31 paused text queues; D32 resume ordered non-generative sync; D33 repeated pause no refill/double version; D34 end with unavailable/blocked cp noRPC/body; D35 end supersedes pending input/control/effects; D36 record_only/typing fence; D37 no new text after end; D38 clock restart/regression/old timer; D39 unknown denies redispatch/new-key; D40 stale version accepted only authenticated safety stop.
D41 normal CAS race no lost update; D42 stop vs reserve/ready publication; D43 input vs delivery-start; D44 effect claim vs crash no redispatch; D45 delivery commit unknown readback/no duplicate; D46 source/context changed prepare->publish.
D47 delivery token/scope/body gate; D48 replay/late result no resurrection; D49 old completion cannot finish new; D50 ready/start/render/interruption distinction; D51 DEBUG both modes every privacy boundary; D52 read-only reconciliation no writes/body/calls/enumeration.
D53 fresh16.15/head/current/check; D54 Legacy upgrade unchanged; D55 downgrade refusal each new table/field marker; D56 empty/legacy downgrade/reupgrade old constraints; D57 actual SQLSTATE+rollback CHECK/FK/unique; D58 default expire_on_commit and independent connections.
D59 CI missing/duplicate/skip/node ownership/manifest attacks; D60 Manager/Runner ACL/process/cleanup unknown; D61 AI Service/C1+Backend Fast+ordinaryPG regression; D62 defaultsclosed/no realProvider/Consent bypass; D63 protectedworktree/index; D64 scope/unknown/production reporting truthful.

Designated PostgreSQL competition: D26,D27,D41,D42,D43,D44,D45,D46. Independent connections, real commits, explicit barriers and bounded waits, zero skips. D13/D18/D19 need SELECT-column instrumentation; D04/D23/D29/D39/D44/D48/D52 need call counts. D53-D56 Manager-only. No test executed during design.

## 9. Freeze gate

Independent reviewers must assess schema/NULL/FKs, exact checkpoint reconstructability, safety queue/fence/resume, output receipt semantics and CI evidence. Close actual blockers then user accepts V0.4 and35 paths before implementation. No frozen claim yet; retention-day absence alone is not a blocker while real policy remains gated.


## 10. Independent-review resolutions (V0.3 normative detail)

### CR-S01: version identities

Persist State.contract_version/Turn.contract_version/result_state_contract_version as interview-agent.v3 only. All mirror schema enums and CHECK branches use this short value. integration_profile carries the 34-character synthetic profile in its separate VARCHAR64. Kernel version remains reminiscence-dialogue.synthetic.v1 in checkpoint and wire kernel_version. Never place the profile in String32. D02/D10/D53/D57 explicitly cover all three identities and actual column lengths.

### CR-S02: complete Context reconstruction

Freeze every ContextSnapshot field, not merely references:
- id and scope stored exactly; purpose=dialogue; manifest_id/version stored exactly.
- selection_refs always empty for this profile; source_refs order equals stored full refs.
- sources reconstructed from exact permitted Message content plus explicitly stored available state/fingerprint at snapshot creation; current restriction always denies hydration rather than rewriting the snapshot.
- recent_history order: original sequence, role, source ref OR response_id, frozen delivery enum; body comes from original Message or bound output Message. delivery enum in an older context never follows current effect state.
- summary_entries order: label enum plus exact quote ref/start/end; quote.text reconstructed by code-point slice of the original, never regenerated summary. C1's deterministic build_context can produce nonempty summaries, so they are supported, not silently omitted.
- asked_keys/skipped_keys tuples and context_revision stored exactly. Policy snapshot comes from checkpoint metadata, never runtime latest.
Compare canonical digest and deterministic Context UUID before use. D14 includes old started snapshot after current receipt becomes delivered/interrupted; every label category and nonempty omitted-history summary, restart and exact order.

### CR-L01: legal explicit Context refresh without changing C1

The only adoption events remain user_message_committed and explicit replace_selection. Normal tick/request/callback never carries a different Context.
Before a manual/automatic generation trigger, Backend compares the pinned context with actually committed input/output/history receipts. If changed, it must apply a separately recorded INTERNAL context_refresh Turn whose C1 payload is replace_selection. This is an explicit context snapshot replacement, not a claim that the user selected other documents. External selection membership remains empty; no additional Session or document source is admitted. Context revision and manifest snapshot version both increase by exactly1, as current C1 _adopt_context requires. Record origin=published_history_refresh in metadata. Policy and scope cannot change.
A refresh Turn stores parent_turn_id (nullable UUID self FK on (session_id,id) NO ACTION DEFERRABLE), internal_reason enum and the exact proposed Context ID/revision. One unique(parent_turn_id,internal_reason) internal child for history refresh. Add these nullable fields to existing Turn, old rows NULL. Child event/key IDs are stable UUID5(parent.id,context_refresh); internal keys are checked against existing rows on collision, never adopt a client-created matching key. Public parent command cannot publish generation before its child completes.
Queue scheduling: a normal parent holds the State.active_command_id coordination slot while remaining queued; its internal child alone enters preparing as the parent's explicit prerequisite before the parent's request event. Child has its own command_order and applied kernel seq; no other normal parent may jump ahead. Input already queued before that parent is applied first. End/safety fence may supersede both. Ordinary ordering is by command_order with this sole explicit parent-prerequisite exception. Parent application uses the post-child core version; client expected_version was checked only at initial acceptance, not silently rewritten as a new client request.
Pure child RPC crash retries only its frozen input and same event/key, first checking whether applied_seq/result already committed. Committed refresh cannot repeat or advance manifest/epoch twice. Stale CAS discards the proposal; no new context chosen behind same event identity. A newer safety fence discards parent/child, not auto-rebase.
Refresh C1 effects are cancellation/stop only. Do not refresh while a visible response is actively delivering just to bypass the C1 generation preconditions. Ready/unstarted output must be explicitly canceled or completed first. Delivered/interrupted history can be included with frozen state. After refresh, original C1 dedup/asked_keys allows the next distinct question with no new user input. D65 (added): two manual requests with no new user input produce distinct eligible questions; interrupted-history, refresh-commit crash/readback, refresh-vs-pause, child key collision, repeated apply each covered. D66: same snapshot no gratuitous refresh, exact two revision increments only on actual context change, no tick/callback context smuggling.

### CR-L02: old effects versus UNKNOWN priority

Add effect fields dispatch_outcome VARCHAR16 NN not_sent/sent/returned/unknown, observed_at nullable UTC, observation_code nullable safe enum. They are execution evidence, never a second publication authority.
Safety fence applies under the Session lock to ALL older-fence generation states:
- reserved -> discarded (not_sent, never dispatch).
- claimed -> discarded, keep dispatch_outcome sent/unknown observation; a running call need not actually stop. Never redispatch it.
- ready -> discarded, revoke its paired unstarted delivery; clear obsolete checkpoint ready slot when synchronized.
- published/delivery-started -> retain stable output reference and mark delivery interrupted/revoke continuation; C1 synchronization updates question receipt. Completed history remains history with dependency gate.
- failed/discarded/completed/unknown terminal publication status is never revived.
Busy index covers ONLY active publication states reserved/claimed/ready; discarded old effects no longer monopolize the Session. All outcomes first lock and compare current fence, THEN decide authority. For old-fence discarded effects, late ready/timeout/process-recovery only updates safe dispatch observation (once), never marks current Session unknown, changes its checkpoint, releases budget, writes body or touches G2. Generation was synthetic/billing not applicable; this is not a real Provider/billing UNKNOWN resolution.
If outcome becomes unknown while still CURRENT fence before stop, atomically mark effect unknown and Session blocked/unavailable. This is terminal here; pause/resume/new-key cannot clear it, only end/new Session. If stop commits FIRST, later unknown is an old discarded observation and cannot block resumed G2. This transaction order is deterministic; tests must prove both orders. No real-provider policy is weakened; future real attempts/fees retain their separately approved UNKNOWN policy.
D67: claimed G1->pause->resume->G2 followed by old ready/timeout/process-recovery; G2 and receipts unchanged, G1 never redispatched, observation truthful, old busy slot released. D68: unknown-first blocks before/after pause and denies new keys, while stop-first does not retroactively block G2; record no fake zero usage/cancellation success.

### CR-L03: idle/initializing cases

State bootstrap may exist idle before C1 start. A fresh start initializes empty pinned Context and applies C1 start before reporting listening. Messages/typing/request/resume before successful start reject START_REQUIRED without writing Message or an unappliable C1 event. No input is claimed accepted in that rejection.
Idle pause with no applied start is a completed Backend no-op (not_started), not effective paused, no C1 pause event or sync requirement. It supersedes any queued/not-applied start/manual/timer normal command and does not leave a paused queue to drain; a later explicit fresh start may proceed. Replaying it does not advance counters. Idle record_only may queue the valid C1 set_mode event (which current kernel accepts before idle guard) and remains idle/no generation; it is synchronized before a later start. End always terminalizes without RPC even during bootstrap or outage.
D69: initialize/idle with service up/down x pause/typing_started/record_only/resume/end; verify exact response, no invalid mandatory event, no permanent sync_required caused by idle pause. Include queued-start superseded by pause and explicit later start.

### CR-C01: preserve B coverage while advancing exact project head

The source scan also finds B Runner fixture hardcodes alembic_version=b196f0d47a21. Therefore two narrowly scoped MODIFIED paths are required: scripts/ci/run_memory_workflow_postgres.py and apps/backend/tests/integration/test_memory_workflow.py.
B script: set exact HEAD=c296a4e8d102 and expected immediate PARENT=b196f0d47a21, separately retain B revision b196 and its historical parent a196 for graph assertion. Upgrade/current/check and Runner actual version use the exact new HEAD. Source manifest includes the new migration plus previous B migration and script/workflow/test hashes. No dynamically chosen head, ancestry relaxation, Manager/Runner privilege change, cleanup change, B_FILE change or node-manifest parameterization.
B integration fixture: change only exact current-project-head check/message from b196 to c296 and leading historical version explanation. Its B identity/allocation/ACL/runtime constraints, EXPECTED45/competition11 membership and test assertions stay unchanged. Run original B script --self-check and verify actual B45/competition11 in its original job at the NEW project head; no baseline-only green substitution.
New dialogue workflow still owns its own Manager migration tests and dialogue runtime nodes. Existing original integration excludes only its new files, original B exclusion remains. D70: both B and dialogue workflows require the new exact head and the b196->c296 parent chain; missing old B fixture/script update is a failing static wiring assertion. Full existing B job and new job must both actually pass before any claim of remote closure.

### Additional checkpoint integrity requirement

metadata_digest binds only metadata; add integrity_key_id VARCHAR100 NN and checkpoint_digest VARCHAR64 NN binding the complete reconstructed canonical State including sensitive leaves, with the existing explicit synthetic integrity key provider and key ID. Missing key/unknown key fails closed; this is an integrity check, not encryption or Consent. Verify after pre-body gates and authorized loading, before transition dispatch. Public errors never contain digest inputs. D71: tampered sensitive leaf with valid metadata fails complete-state integrity; source restrictions still prevent even attempting that body read. No production key implementation is authorized.

### Supplemental queue/crash requirements

Turn stores immutable accepted_at/logical acceptance timestamp and freezes C1 event envelope (event_id, seq,time,core expected_version,input digest,context ref) at preparing claim. Add body-free event_envelope JSON nullable; it is immutable per attempt. Preparing RPC retry requires independent readback: applied terminal=>return metadata; same still-reserved versions=>retry exact pure event explicitly; changed fence=>discard; changed non-fence version=>conflict, never mutate original event behind same ID. Stored source input event is not lost when a stop supersedes a proposal: original Message remains and its source input Turn returns queued for non-generative sync; unexecuted timer/manual-generation parent/child is discarded. End discards input application but leaves saved original with explicit not-consumed metadata.
D72: RPC failure/crash before/after commit, same event envelope and seq/time replay; no automatic generation retry, no unseen command overtaking pending input, saved-source event survives pause while source body is never duplicated in command payload.

V0.3 acceptance IDs now D01-D73, all planned/NOT RUN. New PostgreSQL competition includes D67/D68/D72. Count35 paths:22 new/13 modified. Independent closure must cite this revised artifact hash; V0.2 findings/history preserved.


## 11. CR-L04 targeted correction: coordination ownership versus preparing

This section completes the existing single preparing constraint; no second Session/state authority or worker platform is created.

### 11.1 Durable coordination pointer

State.active_command_id UUID nullable FK (session_id,active_command_id)->Turns(session_id,id), NO ACTION DEFERRABLE INITIALLY DEFERRED. Existing Turn composite unique supports it; add this FK only after that key. Legacy rows NULL, NULL while no coordinator. Pointer is metadata-only and immutable for a claimed application until completion, known failure or safety preemption. No time-based lease takeover or automatic generator retry.
Parent/child self-FK also requires parent_turn_id<>id, internal child depth exactly1 (Schema/Service); root parent has parent_turn_id=NULL. Only a context_refresh child can be this prerequisite. Unique(parent_turn_id,internal_reason) prevents two such child Turns. Normal processing must either acquire an empty active_command_id under State lock or resume the same root after readback; it cannot steal another root's pointer. The pointer grants coordination only; preparing remains the sole RPC event execution slot.

### 11.2 Legal state sequence

1. Eligible public parent P queued; lock State, set active_command_id=P.id. Parent remains queued with no preparing envelope yet. Later normal/callback roots remain queued. Earlier saved input must already have been applied before selecting P.
2. If refresh needed, insert/reuse the one deterministic child C; C alone becomes preparing, freezes its input/event envelope and reserves current checkpoint/version. P stays queued. Release locks and make pure transition RPC for C.
3. Commit C completed and its new checkpoint/manifest/epoch under CAS, clear no pointer (still P). No generation call occurs. A crash here leaves a completed child; resume does not refresh again.
4. With completed C (or no refresh needed), P alone becomes preparing; freeze its event against the committed post-child checkpoint. On commit mark P completed, store reserved generate effect if any and clear active_command_id atomically. Actual generate dispatch only after separate durable effect claim, outside transaction.
5. Child RPC crash: explicit apply(P) reads coordinator/child/attempt/checkpoint. Completed child advances step4; preparing child with identical unchanged reservation retries exact PURE event; changed/superseded fence follows step6. No second coordinator, no simultaneous preparing, no implicit unknown commit assumption.
6. Safety stop locks State and supersedes active root/child: child preparing -> discarded; parent manual/timer/request -> discarded; clear active_command_id in same transaction, record fence. Any old RPC reply fails CAS and cannot release a newer root or alter its child. Saved-source root is retained queued for non-generative explicit synchronization as detailed below. Stop's own reducer synchronization can then acquire the coordinator, using no refresh child unless actually needed.
7. Unknown commit uses independent metadata readback before any coordinator claim/reset; absent/ambiguous is outcome_unknown and leaves publication denied. GET never repairs pointers. End clears pointer and never drains old roots. Another pending normal command cannot infer an abandoned reservation from elapsed time alone.

### 11.3 Frozen pure-transition attempts and saved-source preemption

Add Turn.transition_attempts JSON nullable for legacy, strict body-free array for new profile; each item stores attempt ordinal, immutable C1 event envelope/input digest/context ID/version/fence and terminal/applied metadata. Existing event_envelope denotes the current attempt; prior envelope remains in transition_attempts. No attempt body/State/Response snapshot is stored here. Nested shape/append-only are Service rules, not falsely claimed DB enforcement.
Turn.event_id is the stable command identity. C1 event_id is deterministically UUID5(Turn.event_id, transition:<attempt ordinal>); RPC replay of an attempt uses the exact same event ID/seq/time/digest. Do not rewrite an existing attempt's expected version or context.
If pause preempts a preparing source-input event after original Message was committed, preserve that Message and public command identity, record old proposal attempt superseded, and leave the source command queued. Only an explicit apply/resume can create a new NON-GENERATIVE application attempt of that same source, with a new deterministic attempt event ID and current checkpoint. It must first check whether the exact stable source ref is already in committed_refs/applied metadata; if applied, return original result instead. Same human_turn_id and original source are retained; no Message duplication, new source selection, public-request fingerprint change or generation dispatch. A manual/request/timer parent cannot rebase this way and is discarded on preemption.
A waiting source event with no attempted RPC needs no rebased attempt. End never replays saved source events, and reports not-consumed metadata while retaining the original Message. This is the explicit exception permitting durable original input to survive a pause, not an automatic replay of a generation.

D73 (NOT RUN): actual PostgreSQL unique-preparing invariant throughout queued P->preparing C->completed C->preparing P, crash after each durable boundary, concurrent callback and source writer, safety/end preemption, stale reply not clearing newer pointer. Include explicit saved-source retry with new immutable attempt ID, exact RPC retry using original attempt ID, metadata-only UNKNOWN readback and zero duplicate original/output/generator calls. D65/D72 must additionally cover these exact coordinator sequences. Final acceptance range D01-D73; designated PG competition adds D73. Final candidate remains35 paths (22 new/13 modified). V0.2/V0.3 remain historical snapshots, V0.4 is the current targeted-review artifact.
