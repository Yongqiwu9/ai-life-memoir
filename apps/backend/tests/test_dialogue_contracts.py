"""Strict public/wire DTO and integrity tests; no HTTP or external resources."""

import uuid

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppException
from app.schemas import dialogue as c
from app.services.dialogue_checkpoint import merge, split
from app.services.dialogue_policy import Integrity


@pytest.mark.parametrize(
    "field,value",
    [
        ("expected_version", True),
        ("expected_version", -1),
        ("expected_version", "1"),
        ("provider", "mock"),
        ("synthetic", True),
        ("scope", {}),
        ("time_ms", 1),
    ],
)
def test_public_command_rejects_untrusted_fields(field, value):
    with pytest.raises(ValidationError):
        c.CommandCreate.model_validate({"action": "start", "expected_version": 0, field: value})


@pytest.mark.parametrize(
    "action",
    [
        "response_ready",
        "source_restricted",
        "silence_elapsed",
        "replace_selection",
        "speech_started",
    ],
)
def test_internal_events_not_public_commands(action):
    with pytest.raises(ValidationError):
        c.CommandCreate(action=action, expected_version=0)


def test_key_version_and_sensitive_fingerprint_integrity():
    key = Integrity({"current": b"x" * 32, "old": b"y" * 32}, "current")
    signature = key.sign({"body": "synthetic"}, "old")
    key.verify({"body": "synthetic"}, signature, "old")
    with pytest.raises(AppException):
        key.verify({"body": "changed"}, signature, "old")
    with pytest.raises(AppException):
        key.sign({}, "missing")


def test_storage_and_integration_versions_fit_distinct_columns():
    assert len(c.STORAGE_VERSION) <= 32 and len(c.PROFILE) == 34
    assert c.STORAGE_VERSION != c.PROFILE != c.CONTRACT_VERSION


def test_split_merge_of_idle_state_preserves_all_fields():
    scope = c.DialogueScope(**{k: uuid.uuid4() for k in c.DialogueScope.model_fields})
    policy = c.Policy(
        version="test",
        complete_pause_ms=1,
        uncertain_pause_ms=2,
        max_events=10,
        max_sources=10,
        max_context_chars=100,
        max_history_items=2,
        max_summary_entries=2,
        mode="light",
    )
    state = c.DialogueState(
        scope=scope,
        policy=policy,
        context_id=uuid.uuid4(),
        context_revision=1,
        context_digest="a" * 64,
        manifest_id=uuid.uuid4(),
        manifest_version=1,
    )
    metadata, leaves = split(state)
    assert set(metadata) == set(c.DialogueState.model_fields)
    assert merge(metadata, leaves) == state


@pytest.mark.parametrize(
    "field",
    [
        "call_id",
        "scope",
        "persistence_version",
        "stop_fence",
        "input_digest",
        "context_id",
        "context_revision",
    ],
)
def test_client_rejects_every_header_binding_mismatch(field):
    import json

    from app.services import dialogue_checkpoint as cp
    from app.services.dialogue_client import checked_reply

    scope = c.DialogueScope(**{key: uuid.uuid4() for key in c.DialogueScope.model_fields})
    policy = c.Policy(
        version="synthetic-wire.v1",
        complete_pause_ms=1,
        uncertain_pause_ms=2,
        max_events=10,
        max_sources=10,
        max_context_chars=100,
        max_history_items=2,
        max_summary_entries=2,
        mode="light",
    )
    context = cp.context_value(scope, 1, uuid.uuid4(), 1, [], [], [], [], [])
    values = {
        "profile": c.PROFILE,
        "kernel_version": c.CONTRACT_VERSION,
        "operation": "initialize",
        "call_id": uuid.uuid4(),
        "scope": scope,
        "persistence_version": 0,
        "stop_fence": 0,
        "context": context,
        "policy": policy,
        "state": None,
        "event": None,
        "effect": None,
    }
    request = c.WireRequest(**values, input_digest=c.canonical_digest(values))
    initial = c.DialogueState(
        scope=scope,
        policy=policy,
        context_id=context.id,
        context_revision=1,
        context_digest=c.canonical_digest(context),
        manifest_id=context.manifest_id,
        manifest_version=1,
    )
    reply = c.WireReply(
        operation="initialize",
        call_id=request.call_id,
        scope=scope,
        persistence_version=0,
        stop_fence=0,
        input_digest=request.input_digest,
        context_id=context.id,
        context_revision=1,
        initial_state=initial,
    )
    assert checked_reply(request, reply) == reply
    changed = reply.model_dump(mode="json")
    if field in {"call_id", "context_id"}:
        changed[field] = str(uuid.uuid4())
    elif field == "scope":
        changed[field]["actor_user_id"] = str(uuid.uuid4())
    elif field == "input_digest":
        changed[field] = "0" * 64
    else:
        changed[field] += 1
    with pytest.raises(AppException) as caught:
        checked_reply(request, json.dumps(changed))
    assert caught.value.code == "DIALOGUE_INVALID_RESPONSE" and caught.value.status_code == 502
