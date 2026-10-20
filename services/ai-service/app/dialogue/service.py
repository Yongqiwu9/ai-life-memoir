"""Stateless entry points; a transition cannot execute generation effects."""

from app.dialogue.controller import create_state, reduce_event
from app.dialogue.provider import OfflineDialogueProvider
from app.dialogue.runner import run_effect
from app.dialogue.wire import WireReply, WireRequest


def execute(request: WireRequest, provider: OfflineDialogueProvider | None = None) -> WireReply:
    request = WireRequest.model_validate(request)
    values = {
        "operation": request.operation,
        "call_id": request.call_id,
        "scope": request.scope,
        "persistence_version": request.persistence_version,
        "stop_fence": request.stop_fence,
        "input_digest": request.input_digest,
        "context_id": request.context.id,
        "context_revision": request.context.context_revision,
    }
    if request.operation == "initialize":
        values["initial_state"] = create_state(request.scope, request.policy, request.context)
    elif request.operation == "transition":
        values["transition"] = reduce_event(
            request.state, request.event, request.policy, request.context
        )
    else:
        values["generation"] = run_effect(request.effect, request.context, provider)
    return WireReply(**values)
