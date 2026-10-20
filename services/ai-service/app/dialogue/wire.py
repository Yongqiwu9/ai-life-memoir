"""Versioned, authenticated transport envelopes around the unchanged C1 kernel."""

from typing import Literal
from uuid import UUID

from pydantic import model_validator

from app.dialogue.contracts import (
    CONTRACT_VERSION,
    ContextSnapshot,
    DialogueScope,
    DialogueState,
    Digest,
    Event,
    FailurePayload,
    FrozenDTO,
    GenerateEffect,
    NonNegativeInt,
    Policy,
    ReadyPayload,
    Transition,
    canonical_digest,
)

PROFILE = "session-text-dialogue.synthetic.v1"
STORAGE_VERSION = "interview-agent.v3"


class WireRequest(FrozenDTO):
    profile: Literal["session-text-dialogue.synthetic.v1"] = PROFILE
    kernel_version: Literal["reminiscence-dialogue.synthetic.v1"] = CONTRACT_VERSION
    operation: Literal["initialize", "transition", "generate"]
    call_id: UUID
    scope: DialogueScope
    persistence_version: NonNegativeInt
    stop_fence: NonNegativeInt
    context: ContextSnapshot
    policy: Policy
    state: DialogueState | None = None
    event: Event | None = None
    effect: GenerateEffect | None = None
    input_digest: Digest

    @model_validator(mode="after")
    def bound(self):
        expected = {
            "initialize": (False, False, False),
            "transition": (True, True, False),
            "generate": (False, False, True),
        }[self.operation]
        if tuple(x is not None for x in (self.state, self.event, self.effect)) != expected:
            raise ValueError("Invalid operation shape")
        if self.context.scope != self.scope or any(
            value is not None and value.scope != self.scope
            for value in (self.state, self.event, self.effect)
        ):
            raise ValueError("Invalid scope")
        if self.context.selection_refs or any(
            ref.kind != "message"
            or ref.origin != "user_text"
            or ref.version_id != ref.entity_id
            or ref.version != 1
            or ref.source_scope.origin_session_id != self.scope.session_id
            for ref in self.context.source_refs
        ):
            raise ValueError("Invalid source profile")
        if (
            canonical_digest(self.model_dump(mode="json", exclude={"input_digest"}))
            != self.input_digest
        ):
            raise ValueError("Invalid input digest")
        return self


class WireReply(FrozenDTO):
    profile: Literal["session-text-dialogue.synthetic.v1"] = PROFILE
    kernel_version: Literal["reminiscence-dialogue.synthetic.v1"] = CONTRACT_VERSION
    operation: Literal["initialize", "transition", "generate"]
    call_id: UUID
    scope: DialogueScope
    persistence_version: NonNegativeInt
    stop_fence: NonNegativeInt
    input_digest: Digest
    context_id: UUID
    context_revision: NonNegativeInt
    initial_state: DialogueState | None = None
    transition: Transition | None = None
    generation: ReadyPayload | FailurePayload | None = None

    @model_validator(mode="after")
    def shaped(self):
        expected = {
            "initialize": (True, False, False),
            "transition": (False, True, False),
            "generate": (False, False, True),
        }[self.operation]
        if (
            tuple(x is not None for x in (self.initial_state, self.transition, self.generation))
            != expected
        ):
            raise ValueError("Invalid reply shape")
        return self
