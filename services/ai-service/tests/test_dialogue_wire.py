"""Pure wire/kernel tests. No transport or app server is started."""

from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_dialogue_contracts import make_context, make_policy, make_scope

from app.dialogue import contracts as c
from app.dialogue.mock import DeterministicDialogueMock
from app.dialogue.service import execute
from app.dialogue.wire import WireRequest


def request(operation="initialize", **changes):
    scope, policy = make_scope(), make_policy()
    values = {
        "profile": "session-text-dialogue.synthetic.v1",
        "kernel_version": c.CONTRACT_VERSION,
        "operation": operation,
        "call_id": uuid4(),
        "scope": scope,
        "persistence_version": 0,
        "stop_fence": 0,
        "context": make_context(scope=scope, sources=()),
        "policy": policy,
        "state": None,
        "event": None,
        "effect": None,
    }
    values.update(changes)
    return WireRequest(**values, input_digest=c.canonical_digest(values))


def test_initialize_wire_calls_same_core_without_generation():
    provider = DeterministicDialogueMock()
    data = request()
    response = execute(data, provider)
    assert response.initial_state.scope == data.scope
    assert response.initial_state.status == "idle" and provider.calls == 0
    assert response.input_digest == data.input_digest


def test_transition_does_not_execute_generation_effect():
    provider = DeterministicDialogueMock()
    data = request()
    initial = execute(data).initial_state
    event = c.Event(
        event_id=uuid4(),
        seq=1,
        time_ms=0,
        scope=initial.scope,
        expected_version=0,
        payload=c.StartPayload(),
    )
    start = request(
        "transition",
        scope=initial.scope,
        context=data.context,
        policy=data.policy,
        state=initial,
        event=event,
    )
    started = execute(start, provider).transition.next_state
    event = c.Event(
        event_id=uuid4(),
        seq=2,
        time_ms=1,
        scope=started.scope,
        expected_version=1,
        payload=c.RequestResponsePayload(),
    )
    reserve = request(
        "transition",
        scope=initial.scope,
        context=data.context,
        policy=data.policy,
        state=started,
        event=event,
    )
    result = execute(reserve, provider)
    assert result.transition.next_state.status == "generating"
    assert len(result.transition.effects) == 1 and provider.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile", "live"),
        ("kernel_version", "v0"),
        ("persistence_version", True),
        ("stop_fence", -1),
        ("input_digest", "0" * 64),
        ("provider", "real"),
        ("credential", "forbidden"),
    ],
)
def test_wire_rejects_invalid_binding_and_extra_fields(field, value):
    data = request().model_dump(mode="json")
    data[field] = value
    import json

    with pytest.raises(ValidationError):
        WireRequest.model_validate_json(json.dumps(data))


def test_generation_requires_explicit_effect_not_state_event():
    with pytest.raises(ValidationError):
        request("generate")
