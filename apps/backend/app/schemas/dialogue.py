"""Strict wire mirror of the sealed C1 DTOs; no reducer or provider implementation."""

import hashlib
import json
import unicodedata
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)

CONTRACT_VERSION = "reminiscence-dialogue.synthetic.v1"
MAX_NORMALIZED_QUESTION_CHARS = 2000
ACK_TEXTS = ("嗯，我在听。", "您可以慢慢想，我在听。", "好的，您慢慢说。")
NEUTRAL_QUESTIONS = (
    "您想先从哪段回忆说起？",
    "您愿意接着讲讲吗？",
    "您愿意继续说说吗？",
    "您想从哪段回忆开始讲起？",
    "您还想补充些什么？",
    "接下来，您希望聊些什么？",
)

PositiveInt = Annotated[int, Field(strict=True, gt=0)]
NonNegativeInt = Annotated[int, Field(strict=True, ge=0)]


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("A nonblank value is required")
    return value


Key = Annotated[str, Field(strict=True, min_length=1, max_length=128), AfterValidator(_nonblank)]
Digest = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
SemanticHint = Literal["complete", "incomplete", "unknown"]
Mode = Literal["light", "record_only"]
Outcome = Literal["ack", "question", "no_reply"]
ErrorCode = Literal[
    "INVALID_EVENT",
    "EVENT_CONFLICT",
    "SEQUENCE_GAP",
    "STALE_VERSION",
    "CONTEXT_LIMIT",
    "SOURCE_UNAVAILABLE",
    "INVALID_RESPONSE",
    "PROVIDER_FAILED",
]


class DialogueError(Exception):
    """A controlled error deliberately carrying no input or provider body."""

    def __init__(self, code: ErrorCode = "INVALID_EVENT"):
        allowed = {
            "INVALID_EVENT",
            "EVENT_CONFLICT",
            "SEQUENCE_GAP",
            "STALE_VERSION",
            "CONTEXT_LIMIT",
            "SOURCE_UNAVAILABLE",
            "INVALID_RESPONSE",
            "PROVIDER_FAILED",
        }
        self.code: ErrorCode = code if code in allowed else "INVALID_EVENT"
        super().__init__(self.code)


def _canonical(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, tuple | list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    return value


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        _canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def source_fingerprint(text: str) -> str:
    """Fingerprint a fixture revision, not a privacy or identity credential."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_question(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", text).casefold()
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


class FrozenDTO(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, revalidate_instances="always", strict=True
    )

    @field_validator("*", mode="after")
    @classmethod
    def reject_blank_strings(cls, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("A nonblank value is required")
        return value


class DialogueScope(FrozenDTO):
    actor_user_id: UUID
    family_id: UUID
    family_member_id: UUID
    interview_id: UUID
    session_id: UUID


class SourceScope(FrozenDTO):
    owner_user_id: UUID
    family_id: UUID
    family_member_id: UUID
    origin_interview_id: UUID | None = None
    origin_session_id: UUID | None = None

    @model_validator(mode="after")
    def paired_origin(self):
        if (self.origin_interview_id is None) != (self.origin_session_id is None):
            raise ValueError("Origin identifiers must be both present or both absent")
        return self


class SourceVersionRef(FrozenDTO):
    kind: Literal["message", "document_version"]
    entity_id: UUID
    version_id: UUID
    version: PositiveInt
    source_scope: SourceScope
    origin: Literal["user_text", "voice_final", "document"]

    @model_validator(mode="after")
    def origin_matches_kind(self):
        if self.kind == "message":
            if self.origin == "document" or self.source_scope.origin_session_id is None:
                raise ValueError("Message sources require their original session")
        elif self.origin != "document":
            raise ValueError("Document versions retain their document identity")
        return self


class FixtureSource(FrozenDTO):
    ref: SourceVersionRef
    text: Annotated[str, Field(strict=True, min_length=1, max_length=100_000)]
    availability: Literal["available", "restricted"]
    revision_fingerprint: Digest


class SourceRevisionReceipt(FrozenDTO):
    ref: SourceVersionRef
    revision_fingerprint: Digest


class SelectionManifest(FrozenDTO):
    id: UUID
    version: PositiveInt
    purpose: Literal["dialogue", "extraction"]
    ordered_refs: tuple[SourceVersionRef, ...]
    scope: DialogueScope

    @model_validator(mode="after")
    def distinct_refs(self):
        if len(set(self.ordered_refs)) != len(self.ordered_refs):
            raise ValueError("Selection references must be unique")
        return self


class SourceQuote(FrozenDTO):
    ref: SourceVersionRef
    start: NonNegativeInt
    end: PositiveInt
    text: Annotated[str, Field(strict=True, min_length=1, max_length=100_000)]

    @model_validator(mode="after")
    def ordered_interval(self):
        if self.end <= self.start:
            raise ValueError("A quote must have a nonempty ordered interval")
        return self


class SummaryEntry(FrozenDTO):
    quote: SourceQuote
    label: Literal["topic", "person", "time", "uncertain", "conflict"]


class HistoryItem(FrozenDTO):
    sequence: PositiveInt
    ref: SourceVersionRef | None = None
    role: Literal["user", "assistant"]
    text: Annotated[str, Field(strict=True, min_length=1, max_length=100_000)]
    delivery: Literal["none", "started", "delivered", "interrupted"] = "none"
    response_id: UUID | None = None

    @model_validator(mode="after")
    def role_provenance(self):
        if self.role == "user":
            if (
                self.ref is None
                or self.ref.kind != "message"
                or self.delivery != "none"
                or self.response_id is not None
            ):
                raise ValueError("User history requires a user message reference")
        elif self.ref is not None:
            raise ValueError("Assistant history is not a user source")
        return self


class Policy(FrozenDTO):
    version: Key
    complete_pause_ms: PositiveInt
    uncertain_pause_ms: PositiveInt
    max_events: PositiveInt
    max_sources: PositiveInt
    max_context_chars: PositiveInt
    max_history_items: PositiveInt
    max_summary_entries: PositiveInt
    mode: Mode

    @model_validator(mode="after")
    def ordered_pauses(self):
        if self.complete_pause_ms > self.uncertain_pause_ms:
            raise ValueError("Complete pause must not exceed uncertain pause")
        return self


class ContextSnapshot(FrozenDTO):
    id: UUID
    scope: DialogueScope
    purpose: Literal["dialogue"] = "dialogue"
    manifest_id: UUID
    manifest_version: PositiveInt
    selection_refs: tuple[SourceVersionRef, ...] = ()
    source_refs: tuple[SourceVersionRef, ...]
    sources: tuple[FixtureSource, ...]
    recent_history: tuple[HistoryItem, ...]
    summary_entries: tuple[SummaryEntry, ...]
    asked_keys: tuple[Key, ...]
    skipped_keys: tuple[Key, ...]
    context_revision: PositiveInt

    @model_validator(mode="after")
    def unique_source_identity(self):
        if len(set(self.source_refs)) != len(self.source_refs):
            raise ValueError("Context source references must be unique")
        if len(set(self.selection_refs)) != len(self.selection_refs):
            raise ValueError("Selected references must be unique")
        if tuple(source.ref for source in self.sources) != self.source_refs:
            raise ValueError("Context bodies and references must have identical order")
        if not set(self.selection_refs).issubset(self.source_refs):
            raise ValueError("Selected references must be included")
        return self


GENERATION_BINDING_FIELDS = (
    "request_id",
    "scope",
    "reservation_version",
    "policy_version",
    "epoch",
    "context_id",
    "context_revision",
    "manifest_id",
    "manifest_version",
    "silence_cycle",
    "trigger",
    "allowed_outcomes",
)


class GenerationBinding(FrozenDTO):
    request_id: UUID
    scope: DialogueScope
    reservation_version: NonNegativeInt
    policy_version: Key
    epoch: NonNegativeInt
    context_id: UUID
    context_revision: PositiveInt
    manifest_id: UUID
    manifest_version: PositiveInt
    silence_cycle: NonNegativeInt
    trigger: Literal["auto", "manual"]
    allowed_outcomes: tuple[Outcome, ...]

    @model_validator(mode="after")
    def outcomes_valid(self):
        if not self.allowed_outcomes or len(set(self.allowed_outcomes)) != len(
            self.allowed_outcomes
        ):
            raise ValueError("At least one distinct outcome is required")
        if self.trigger == "manual" and self.allowed_outcomes != ("question", "no_reply"):
            raise ValueError("Manual requests allow a question or no reply")
        return self


def generation_binding(value: GenerationBinding) -> dict[str, Any]:
    return {name: getattr(value, name) for name in GENERATION_BINDING_FIELDS}


class GenerateEffect(GenerationBinding):
    kind: Literal["generate"] = "generate"
    effect_id: UUID
    dependency_refs: tuple[SourceVersionRef, ...] = ()


class Response(GenerationBinding):
    effect_id: UUID
    response_id: UUID
    outcome: Outcome
    text: Annotated[str, Field(strict=True, min_length=1, max_length=2000)] | None = None
    question_key: Key | None = None
    topic_key: Key | None = None
    basis_kind: Literal["none", "neutral", "sourced"] = "none"
    basis_quotes: tuple[SourceQuote, ...] = ()

    @model_validator(mode="after")
    def outcome_shape(self):
        if self.outcome not in self.allowed_outcomes:
            raise ValueError("Outcome is not allowed for this reservation")
        if self.outcome == "no_reply":
            if (
                self.text is not None
                or self.question_key is not None
                or self.topic_key is not None
                or self.basis_kind != "none"
                or self.basis_quotes
            ):
                raise ValueError("No-reply results cannot contain content")
        elif self.outcome == "ack":
            if (
                self.text not in ACK_TEXTS
                or self.question_key is not None
                or self.topic_key is not None
                or self.basis_kind != "none"
                or self.basis_quotes
            ):
                raise ValueError("Acknowledgements must be neutral fixed phrases")
        elif (
            self.text is None
            or self.question_key is None
            or self.topic_key is None
            or self.basis_kind == "none"
            or (self.basis_kind == "neutral" and self.basis_quotes)
            or (self.basis_kind == "sourced" and not self.basis_quotes)
        ):
            raise ValueError("Questions require keys and a valid kind of basis")
        return self


class QuestionReceipt(FrozenDTO):
    request_id: UUID
    response_id: UUID
    epoch: NonNegativeInt
    question_key: Key
    topic_key: Key
    normalized_text: Annotated[
        str, Field(strict=True, min_length=1, max_length=MAX_NORMALIZED_QUESTION_CHARS)
    ]
    delivery: Literal["started", "delivered", "interrupted"]
    basis_refs: tuple[SourceVersionRef, ...]


class DeliveryReceipt(FrozenDTO):
    request_id: UUID
    response_id: UUID
    policy_version: Key
    epoch: NonNegativeInt
    context_id: UUID
    context_revision: PositiveInt
    manifest_id: UUID
    manifest_version: PositiveInt
    kind: Literal["started", "completed"]


class ReadyPayload(GenerationBinding):
    kind: Literal["response_ready"] = "response_ready"
    response: Response


class FailurePayload(GenerationBinding):
    kind: Literal["response_failed"] = "response_failed"
    error_code: ErrorCode


class StartPayload(FrozenDTO):
    kind: Literal["start"] = "start"


class PausePayload(FrozenDTO):
    kind: Literal["pause"] = "pause"


class ResumePayload(FrozenDTO):
    kind: Literal["resume"] = "resume"


class EndPayload(FrozenDTO):
    kind: Literal["end"] = "end"


class SpeechStartedPayload(FrozenDTO):
    kind: Literal["speech_started"] = "speech_started"
    human_turn_id: UUID


class SpeechEndedPayload(FrozenDTO):
    kind: Literal["speech_ended"] = "speech_ended"
    human_turn_id: UUID
    semantic_hint: SemanticHint


class TypingStartedPayload(FrozenDTO):
    kind: Literal["typing_started"] = "typing_started"


class TypingEndedPayload(FrozenDTO):
    kind: Literal["typing_ended"] = "typing_ended"


class UserMessageCommittedPayload(FrozenDTO):
    kind: Literal["user_message_committed"] = "user_message_committed"
    human_turn_id: UUID
    message_ref: SourceVersionRef
    semantic_hint: SemanticHint


class SilenceElapsedPayload(FrozenDTO):
    kind: Literal["silence_elapsed"] = "silence_elapsed"
    human_turn_id: UUID
    silence_cycle: NonNegativeInt


class RequestResponsePayload(FrozenDTO):
    kind: Literal["request_response"] = "request_response"


class DeliveryStartedPayload(FrozenDTO):
    kind: Literal["delivery_started"] = "delivery_started"
    receipt: DeliveryReceipt


class DeliveryCompletedPayload(FrozenDTO):
    kind: Literal["delivery_completed"] = "delivery_completed"
    receipt: DeliveryReceipt


class SetModePayload(FrozenDTO):
    kind: Literal["set_mode"] = "set_mode"
    mode: Mode


class SkipTopicPayload(FrozenDTO):
    kind: Literal["skip_topic"] = "skip_topic"
    topic_key: Key


class UnskipTopicPayload(FrozenDTO):
    kind: Literal["unskip_topic"] = "unskip_topic"
    topic_key: Key


class ReplaceSelectionPayload(FrozenDTO):
    kind: Literal["replace_selection"] = "replace_selection"
    context: ContextSnapshot


class SourceRestrictedPayload(FrozenDTO):
    kind: Literal["source_restricted"] = "source_restricted"
    ref: SourceVersionRef


EventPayload = Annotated[
    StartPayload
    | PausePayload
    | ResumePayload
    | EndPayload
    | SpeechStartedPayload
    | SpeechEndedPayload
    | TypingStartedPayload
    | TypingEndedPayload
    | UserMessageCommittedPayload
    | SilenceElapsedPayload
    | RequestResponsePayload
    | ReadyPayload
    | FailurePayload
    | DeliveryStartedPayload
    | DeliveryCompletedPayload
    | SetModePayload
    | SkipTopicPayload
    | UnskipTopicPayload
    | ReplaceSelectionPayload
    | SourceRestrictedPayload,
    Field(discriminator="kind"),
]


class Event(FrozenDTO):
    event_id: UUID
    seq: PositiveInt
    time_ms: NonNegativeInt
    scope: DialogueScope
    expected_version: NonNegativeInt
    payload: EventPayload

    @property
    def kind(self) -> str:
        return self.payload.kind


class ResultMetadata(FrozenDTO):
    code: Literal[
        "OK",
        "IGNORED",
        "INVALID_EVENT",
        "EVENT_CONFLICT",
        "SEQUENCE_GAP",
        "STALE_VERSION",
        "CONTEXT_LIMIT",
        "SOURCE_UNAVAILABLE",
        "INVALID_RESPONSE",
        "PROVIDER_FAILED",
    ] = "OK"
    disposition: Literal["accepted", "ignored", "replayed", "rejected", "blocked"] = "accepted"
    request_id: UUID | None = None
    response_id: UUID | None = None


class EventReceipt(FrozenDTO):
    event_id: UUID
    digest: Digest
    seq: PositiveInt
    result: ResultMetadata


class HumanTurnRecord(FrozenDTO):
    human_turn_id: UUID
    assigned_cycle: PositiveInt
    semantic_hint: SemanticHint = "unknown"


class DialogueState(FrozenDTO):
    scope: DialogueScope
    contract_version: Literal["reminiscence-dialogue.synthetic.v1"] = CONTRACT_VERSION
    policy: Policy
    status: Literal[
        "idle", "listening", "generating", "ready", "delivering", "paused", "blocked", "ended"
    ] = "idle"
    mode: Mode = "light"
    version: NonNegativeInt = 0
    epoch: NonNegativeInt = 0
    last_seq: NonNegativeInt = 0
    last_time_ms: NonNegativeInt = 0
    speaking: StrictBool = False
    typing: StrictBool = False
    active_speech_turn_id: UUID | None = None
    current_human_turn_id: UUID | None = None
    turn_cycles: tuple[HumanTurnRecord, ...] = ()
    committed_refs: tuple[SourceVersionRef, ...] = ()
    restricted_refs: tuple[SourceVersionRef, ...] = ()
    silence_cycle: NonNegativeInt = 0
    cycle_consumed: StrictBool = False
    auto_suspended: StrictBool = False
    silence_since_ms: NonNegativeInt | None = None
    semantic_hint: SemanticHint = "unknown"
    context_id: UUID
    context_revision: PositiveInt
    context_digest: Digest
    context_source_refs: tuple[SourceVersionRef, ...] = ()
    selection_refs: tuple[SourceVersionRef, ...] = ()
    known_source_revisions: tuple[SourceRevisionReceipt, ...] = ()
    skipped_keys: tuple[Key, ...] = ()
    manifest_id: UUID
    manifest_version: PositiveInt
    pending_effect: GenerateEffect | None = None
    ready_response: Response | None = None
    active_response: Response | None = None
    known_requests: tuple[GenerateEffect, ...] = ()
    question_receipts: tuple[QuestionReceipt, ...] = ()
    event_receipts: tuple[EventReceipt, ...] = ()
    terminal_receipt: EventReceipt | None = None

    @property
    def policy_version(self) -> str:
        return self.policy.version

    @model_validator(mode="after")
    def coherent_state(self):
        expected_slot = {
            "generating": "pending_effect",
            "ready": "ready_response",
            "delivering": "active_response",
        }.get(self.status)
        for name in ("pending_effect", "ready_response", "active_response"):
            if (getattr(self, name) is not None) != (name == expected_slot):
                raise ValueError("Output slots must agree with the state")
        if self.speaking != (self.active_speech_turn_id is not None):
            raise ValueError("Speaking must identify its active human turn")
        ledgers = (
            self.turn_cycles,
            self.committed_refs,
            self.restricted_refs,
            self.known_requests,
            self.question_receipts,
            self.event_receipts,
            self.known_source_revisions,
            self.skipped_keys,
        )
        if any(len(ledger) > self.policy.max_events for ledger in ledgers):
            raise ValueError("State ledgers exceed the fixed policy capacity")
        unique_values = (
            tuple(turn.human_turn_id for turn in self.turn_cycles),
            self.committed_refs,
            self.restricted_refs,
            tuple(request.request_id for request in self.known_requests),
            tuple(receipt.response_id for receipt in self.question_receipts),
            tuple(receipt.event_id for receipt in self.event_receipts),
            tuple(receipt.ref for receipt in self.known_source_revisions),
            self.skipped_keys,
        )
        if any(len(set(values)) != len(values) for values in unique_values):
            raise ValueError("State ledger identities must be unique")
        return self


class CancelGenerationEffect(FrozenDTO):
    kind: Literal["cancel_generation"] = "cancel_generation"
    effect_id: UUID
    request_id: UUID


class StopPlaybackEffect(FrozenDTO):
    kind: Literal["stop_playback"] = "stop_playback"
    effect_id: UUID
    request_id: UUID
    response_id: UUID


class DeliverEffect(FrozenDTO):
    kind: Literal["deliver"] = "deliver"
    effect_id: UUID
    response: Response


class ErrorEffect(FrozenDTO):
    kind: Literal["error"] = "error"
    code: ErrorCode


Effect = Annotated[
    GenerateEffect | CancelGenerationEffect | StopPlaybackEffect | DeliverEffect | ErrorEffect,
    Field(discriminator="kind"),
]


class Transition(FrozenDTO):
    next_state: DialogueState
    effects: tuple[Effect, ...]
    result: ResultMetadata


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


class CommandCreate(FrozenDTO):
    action: Literal[
        "start",
        "request_response",
        "pause",
        "resume",
        "end",
        "typing_started",
        "typing_ended",
        "set_mode",
        "skip_topic",
        "unskip_topic",
    ]
    expected_version: NonNegativeInt
    mode: Mode | None = None
    topic_key: Key | None = None

    @model_validator(mode="after")
    def fields_match(self):
        if (self.action == "set_mode") != (self.mode is not None):
            raise ValueError("Invalid mode")
        if (self.action in {"skip_topic", "unskip_topic"}) != (self.topic_key is not None):
            raise ValueError("Invalid topic")
        return self


class TextCreate(FrozenDTO):
    content: Annotated[str, Field(strict=True, min_length=1, max_length=10_000)]
    human_turn_id: UUID
    expected_version: NonNegativeInt

    @field_validator("human_turn_id", mode="before")
    @classmethod
    def parse_human_turn_id(cls, value):
        # FastAPI validates an already-decoded JSON dict in Python mode.
        # Normalize this public UUID field only; other strict DTOs stay strict.
        if isinstance(value, UUID):
            return value
        if type(value) is str:
            try:
                return UUID(value)
            except ValueError:
                raise ValueError("A valid UUID is required") from None
        raise ValueError("A valid UUID is required")


class DeliveryCreate(FrozenDTO):
    token: Annotated[str, Field(strict=True, min_length=32, max_length=256)]
    expected_version: NonNegativeInt


class ApplyCreate(FrozenDTO):
    expected_version: NonNegativeInt


class StateRead(FrozenDTO):
    session_id: UUID
    contract_version: Literal["interview-agent.v3"] = STORAGE_VERSION
    effective_status: Literal[
        "idle", "listening", "generating", "ready", "delivering", "paused", "blocked", "ended"
    ]
    persistence_version: NonNegativeInt
    core_version: NonNegativeInt
    epoch: NonNegativeInt
    stop_fence: NonNegativeInt
    checkpoint_sync: Literal["valid", "sync_required", "unavailable"]
    session_status: Literal["active", "completed", "cancelled"]
    queued_command_ids: tuple[UUID, ...] = ()
    ready_response_id: UUID | None = None
    delivery_token: str | None = None
    delivery_expires_ms: NonNegativeInt | None = None


class CommandRead(FrozenDTO):
    id: UUID
    session_id: UUID
    execution_status: Literal["queued", "preparing", "completed", "failed", "discarded"]
    message_id: UUID | None = None
    response_id: UUID | None = None
    resulting_version: NonNegativeInt | None = None
    code: str


class DeliveryRead(FrozenDTO):
    command: CommandRead
    output_message_id: UUID | None = None
    text: str | None = None


class DeliveryTicket(FrozenDTO):
    response_id: UUID
    token: str
    expires_ms: NonNegativeInt
