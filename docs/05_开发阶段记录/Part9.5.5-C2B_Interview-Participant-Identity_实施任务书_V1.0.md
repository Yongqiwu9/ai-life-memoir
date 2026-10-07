# Part 9.5.5-C2B — Interview Participant Identity Foundation Implementation Task V1.0

| Metadata | Value |
| --- | --- |
| Status | IMPLEMENTED / AUDIT REMEDIATION COMPLETED / PRE-COMMIT RE-AUDIT PENDING |
| Part | 9.5.5-C2B |
| Parent | Part 9.5.5-C |
| Design Basis | Part 9.5.5-C Design Freeze + C2 Design Addendum V1.0 |
| Implementation Baseline | `8a6de08c7a48ef836d865c2eae6ed53068d81c98` |
| Completion | LOCAL IMPLEMENTATION COMPLETE; NOT COMMITTED OR SEALED |

**Task Spec != Implementation Report. C2B Completed != Part 9.5.5-C Completed.**

## Scope

C2B implements only InterviewParticipant identity relations, speaker-only roles, eligibility and state constraints, Owner/active Collaborator proposals, `participant_confirmation` context-bound identity verification, self claim/confirm, adult autonomous decision declaration, self inactive, minimal rights-scoped self read, durable command idempotency reuse, one Alembic revision, tests and documentation synchronization.

User remains the only authentication principal. FamilyMember remains an archive person. InterviewParticipant is an Interview-scoped participation relation. Operator is an operation actor fact and is not a Participant role.

## Identity and authorization boundaries

- Owner and active Collaborator can create only `proposed` Participant records. They cannot confirm another person.
- Account and rights_only users must complete a `participant_confirmation` challenge before self confirmation.
- `verification_proof` is bound to User, Contact, Challenge and Participant context and is not an account token, rights token, Family permission, Consent or Source authorization.
- `rights_only` can read, confirm and deactivate only its own minimal Participant relation. It gains no archive access.
- Participant inactive is not Consent withdrawal and does not start deletion.

## Persistence decisions

- `interview_id` is nullable with `ON DELETE SET NULL`; immutable `interview_scope_id` preserves historical scope.
- `user_id` uses `ON DELETE RESTRICT`; `family_member_id` uses `ON DELETE SET NULL`.
- `(verified_contact_id, user_id)` references `user_contacts(id, user_id)`; Contact state remains a Service check.
- `verification_ref` stores an AuthChallenge UUID without an FK because Challenge retention is independent.
- V1 roles storage is a constrained scalar `speaker`, exposed by the API as `roles=["speaker"]`.
- Conservative identity uniqueness: `(interview_scope_id, user_id)` is unique whenever `user_id IS NOT NULL`, covering verified, inactive and disputed identity projections. Unclaimed proposals remain unrestricted.
- Composite candidate key `UNIQUE(id, interview_scope_id)` supports a future same-Interview composite FK from SourceSpeakerBinding.
- No historical Participant or identity backfill is permitted.

## Explicit exclusions

ConsentGrant, ConsentEvent, Source/Provenance, RevisionProposal, Deletion, PrivacyOutbox, Sanitization, MemoryCandidate, Memory, Memoir, real audio upload, STT, LLM and RAG are not part of C2B.

## Git safety

Implementation ends with an empty staging area. No commit or push is authorized. The 16 historical template deletions, untracked `ad` and ignored `apps/backend/.env.test` remain untouched.

## Local Implementation Evidence

- InterviewParticipant model, proposal/confirm/inactive services and minimal self read API implemented.
- `participant_confirmation` reuses AuthChallenge and supports separately validated account and rights_only principals.
- Migration `d4f8a1c2b3e6` follows `b7e2c4d891a0`; PostgreSQL current/check report one head and no drift.
- Fast validation: 173 passed / 40 deselected.
- PostgreSQL integration validation: 40 passed / 173 deselected; the C2B PostgreSQL file has 11 passing tests, including fresh migration, empty downgrade/re-upgrade, data-present downgrade safety, real FK actions, database invariants, claim race, double confirm and confirm/inactive concurrency.
- Initial Pre-Commit Audit found three Blocking Medium issues. Audit Remediation #1 closed the SET NULL/immutability conflict and added the composite candidate key. Pre-Commit Re-Audit #1 identified remaining behavior-evidence and documentation gaps; Audit Remediation #2 closed them. Pre-Commit Re-Audit #2, staging, commit, push and remote CI have not started.
- Ruff and format checks passed.
- Participant verified remains distinct from Consent, Source ownership, SourceSpeakerBinding and archive access.
