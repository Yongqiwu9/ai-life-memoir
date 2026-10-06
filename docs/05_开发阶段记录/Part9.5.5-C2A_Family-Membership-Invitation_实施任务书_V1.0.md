# Part 9.5.5-C2A — Family Membership and Invitation Implementation Task V1.0

| Metadata | Value |
| --- | --- |
| Status | IMPLEMENTATION WRITTEN / AUDIT REMEDIATION COMPLETED / PRE-COMMIT RE-AUDIT PENDING |
| Part | 9.5.5-C2A |
| Parent Design | Part 9.5.5-C Design Freeze + C2 Design Addendum V1.0 |
| Implementation Baseline | `0add93b755422afcf69c6029c4c72879405eb98d` |
| Completion | AUDIT REMEDIATION COMPLETE; RE-AUDIT REQUIRED; NOT STAGED / COMMITTED / PUSHED |

**Task Spec != Implementation Report. C2A != entire C2 completion.**

## 1. Scope

C2A implements only:

1. CommandIdempotencyRecord.
2. FamilyInvitation.
3. FamilyMembership.
4. Owner / active Collaborator authorization primitive.
5. `invitation_acceptance` AuthChallenge context.
6. `verification_proof` foundation.
7. Account-bound Contact verification.
8. Invitation APIs.
9. Membership APIs.
10. `families.owner_id` FK CASCADE → RESTRICT.
11. One C2A Alembic revision.
12. Fast, PostgreSQL integration, concurrency and security tests.
13. Necessary documentation synchronization.

Explicitly excluded: InterviewParticipant, `participant_confirmation`, Consent, Source/Provenance, RevisionProposal, Deletion, PrivacyOutbox, Sanitization, MemoryCandidate, Memory and Memoir.

## 2. Ownership and authorization

`Family.owner_id` remains the only Owner authority. Owner, rights_only and system principals cannot have FamilyMembership. Membership role is only `collaborator` and grants collaboration management only; all existing Family, FamilyMember, Interview, Session, Audio, Transcript, Segment and Message content APIs remain Owner-only.

## 3. FamilyMembership

Fields: UUID id/family_id/user_id/accepted_invitation_id, role, state, generation, joined_at, ended_at, created_at, updated_at. Role=`collaborator`; states=`active/revoked/left`; generation starts at 1 and increments on revoke, leave and rejoin. Unique `(family_id,user_id)`; indexes `(user_id,state)` and `(family_id,state)`.

Rejoin uses a new accepted Invitation and reactivates the same Membership row under lock, increments generation, updates joined_at and clears ended_at. Authorization always reads current state/generation and does not bump `User.auth_generation`.

## 4. FamilyInvitation

Fields: UUID id/family_id/requested_by_user_id/recipient_user_id/approved_by_user_id, recipient hash/ciphertext, token digest, state, version, approved_at, accepted_at, expires_at, created_at, updated_at.

States: pending_owner, approved, accepted, rejected, cancelled, revoked, expired. Token digest is unique when non-null. `(family_id,recipient_hash)` is unique while state is pending_owner or approved.

Owner creates approved Invitation. Active Collaborator creates pending_owner Invitation. Only Owner approves/rejects. Requester can cancel a pending_owner Invitation. Owner can revoke an unaccepted approved Invitation. Accept performs Invitation validation, proof validation, Membership create/rejoin and Invitation accepted transition in one transaction.

## 5. Context-bound verification

C2A adds the `invitation_acceptance` context and the two identity verification endpoints defined by the C2 Addendum. Invitation recipient channel is decrypted server-side; the client cannot replace it. Verification issues a short-lived context-bound proof with strict token type, scope, audience, issuer, context, User, Contact and generation checks.

Account verification reuses or creates a verified Contact for the current account. It never creates a rights_only User. Contact collision with another User fails closed; legacy email can be attached only after the same logged-in account completes instantaneous verification.

## 6. Durable idempotency

Add `command_idempotency_records` according to the C2 Addendum. Every C2A public mutation uses Idempotency-Key and a canonical request digest. Record and business mutation commit atomically. Replays return an operation-specific typed safe snapshot; unknown operations, wrong snapshot types, extra fields and undeclared nested objects are rejected by default. Conflicting digests return 409. No secret, token, proof, OTP, PII ciphertext/hash or provider credential may be persisted in response_body. Verification replay preserves the original issued-at and expiry semantics.

## 7. Migration

Create one revision after `c1a7d45e92b0`: command idempotency records, invitations, memberships, constraints/indexes, then replace `families.owner_id` CASCADE FK with RESTRICT. Do not modify historical revisions or create business backfill. New tables start empty.

## 8. Validation

Required validation:

- Ruff check and format check.
- Complete non-integration suite.
- PostgreSQL fresh upgrade/current/check.
- PostgreSQL integration and concurrency tests.
- Post-integration current/check.
- Invitation token/PII/proof/type-confusion/IDOR/privilege/idempotency/generation/provider/secret audit.
- Scope audit proving no C2B, Consent, Source, Deletion, Sanitization or Memory runtime implementation.

## 9. Git safety

Do not stage, commit or push during implementation. Preserve the 16 historical template deletions, untracked `ad`, ignored `apps/backend/.env.test`, and an empty staging area. Completion requires a separate Pre-Commit Audit.

## 10. Local implementation evidence

- Implementation revision: `b7e2c4d891a0`, down revision `c1a7d45e92b0`; single Alembic head.
- Ruff check: PASS. Ruff format check: PASS.
- Fast suite after audit remediation: 161 passed / 29 integration deselected.
- PostgreSQL integration suite after audit remediation: 29 passed / 161 non-integration deselected, including isolated fresh-schema migration, Membership revoke authorization race and C2A concurrency cases.
- Post-integration Alembic current: `b7e2c4d891a0 (head)`; check: `No new upgrade operations detected`.
- Production database migration: NOT RUN.
- Audit remediation: existing content denial matrix, operation-specific safe snapshot allowlist/default-deny behavior, original proof `iat`/`exp` replay semantics, and Membership revoke authorization race covered.
- Git: NOT STAGED / NOT COMMITTED / NOT PUSHED. A separate Pre-Commit Re-Audit remains required.

C2A completion does not complete C2. InterviewParticipant and `participant_confirmation` remain C2B scope. Consent, Source/Provenance, Revision, Deletion, Sanitization and Memory remain later scope.
