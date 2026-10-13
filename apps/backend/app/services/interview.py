import sqlite3
import uuid
from collections.abc import Callable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException, NotFoundException
from app.crud import family as family_crud
from app.crud import family_member as family_member_crud
from app.crud import interview as interview_crud
from app.crud import memory_workflow as workflow_crud
from app.models.interview import Interview
from app.models.memory_workflow import PROTECTED_DELETE_FK_MANIFEST
from app.schemas.interview import InterviewCreate, InterviewUpdate


def _get_owned_member(db: Session, *, user_id: uuid.UUID, member_id: uuid.UUID) -> None:
    member = family_member_crud.get_family_member_by_id(db, member_id=member_id)
    if member is None:
        raise NotFoundException("Family member not found")
    family = family_crud.get_family(db, owner_id=user_id, family_id=member.family_id)
    if family is None:
        raise NotFoundException("Family member not found")


def get_owned_interview(db: Session, *, user_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
    interview = interview_crud.get_interview_by_id(db, interview_id=interview_id)
    if interview is None:
        raise NotFoundException("Interview not found")
    _get_owned_member(db, user_id=user_id, member_id=interview.family_member_id)
    return interview


def create_interview(
    db: Session,
    *,
    user_id: uuid.UUID,
    member_id: uuid.UUID,
    data: InterviewCreate,
) -> Interview:
    _get_owned_member(db, user_id=user_id, member_id=member_id)
    return interview_crud.create_interview(
        db,
        family_member_id=member_id,
        title=data.title,
        type_=data.type.value,
    )


def get_interview(db: Session, *, user_id: uuid.UUID, interview_id: uuid.UUID) -> Interview:
    return get_owned_interview(db, user_id=user_id, interview_id=interview_id)


def list_interviews(
    db: Session,
    *,
    user_id: uuid.UUID,
    member_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[Interview], int]:
    _get_owned_member(db, user_id=user_id, member_id=member_id)
    offset = (page - 1) * page_size
    return interview_crud.list_interviews(
        db,
        family_member_id=member_id,
        offset=offset,
        limit=page_size,
    )


def update_interview(
    db: Session,
    *,
    user_id: uuid.UUID,
    interview_id: uuid.UUID,
    data: InterviewUpdate,
) -> Interview:
    interview = get_owned_interview(db, user_id=user_id, interview_id=interview_id)
    values: dict[str, str] = {}
    if data.title is not None:
        values["title"] = data.title
    if data.status is not None:
        values["status"] = data.status.value
    if data.type is not None:
        values["type"] = data.type.value
    if not values:
        return interview
    return interview_crud.update_interview(db, interview=interview, values=values)


def delete_interview(db: Session, *, user_id: uuid.UUID, interview_id: uuid.UUID) -> None:
    interview = interview_crud.get_owned_interview(db, owner_id=user_id, interview_id=interview_id)
    if interview is None:
        raise NotFoundException("Interview not found")
    _delete_with_reference_guard(
        db,
        has_references=lambda: (
            interview_crud.has_protected_references(db, interview_id=interview_id)
            or workflow_crud.has_workflow_references(
                db, scope_kind="interview", scope_id=interview_id
            )
        ),
        delete=lambda: interview_crud.delete_interview(db, interview=interview, owner_id=user_id),
        constraint_names={"memories_source_message_id_fkey"},
        reauthorize=lambda: _require_delete_owner(db, user_id, interview_id),
        not_found_message="Interview not found",
    )


def _require_delete_owner(db: Session, user_id: uuid.UUID, interview_id: uuid.UUID) -> None:
    if interview_crud.get_owned_interview(db, owner_id=user_id, interview_id=interview_id) is None:
        raise NotFoundException("Interview not found")


def _rollback_or_unknown(db: Session) -> None:
    try:
        db.rollback()
    except Exception:  # noqa: BLE001 -- rollback failure makes the outcome unknown
        raise AppException(
            "Resource deletion outcome is unknown",
            code="RESOURCE_DELETE_OUTCOME_UNKNOWN",
            status_code=503,
        ) from None


def _delete_with_reference_guard(
    db: Session,
    *,
    has_references: Callable[[], bool],
    delete: Callable[[], bool | None],
    constraint_names: set[str],
    reauthorize: Callable[[], None] | None = None,
    not_found_message: str = "Resource not found",
) -> None:
    """Authorized caller owns this request session; no HTTP-layer rollback."""
    committing = False
    try:
        if has_references():
            _rollback_or_unknown(db)
            raise AppException(
                "Resource is referenced and cannot be deleted",
                code="RESOURCE_IN_USE",
                status_code=409,
            )
        if delete() is False:
            raise NotFoundException(not_found_message)
        committing = True
        db.commit()
    except IntegrityError as exc:
        _rollback_or_unknown(db)
        original = exc.orig
        diagnostic = getattr(original, "diag", None)
        pair = (
            getattr(diagnostic, "table_name", None),
            getattr(diagnostic, "constraint_name", None),
        )
        legacy_pairs = {
            ("memories", "memories_source_message_id_fkey"),
            ("memories", "memories_family_member_id_fkey"),
            ("memoirs", "memoirs_family_member_id_fkey"),
        }
        permitted = {item for item in legacy_pairs if item[1] in constraint_names} | set(
            PROTECTED_DELETE_FK_MANIFEST
        ) - legacy_pairs
        postgres_reference = getattr(original, "sqlstate", None) == "23503" and pair in permitted
        sqlite_foreign_key = (
            isinstance(original, sqlite3.IntegrityError)
            and getattr(original, "sqlite_errorcode", None)
            in (sqlite3.SQLITE_CONSTRAINT_FOREIGNKEY, sqlite3.SQLITE_CONSTRAINT_TRIGGER)
            and str(original) == "FOREIGN KEY constraint failed"
        )
        if postgres_reference or sqlite_foreign_key:
            try:
                if reauthorize is not None:
                    reauthorize()
                confirmed = postgres_reference or has_references()
            except Exception:
                _rollback_or_unknown(db)
                raise
            _rollback_or_unknown(db)
            if confirmed:
                raise AppException(
                    "Resource is referenced and cannot be deleted",
                    code="RESOURCE_IN_USE",
                    status_code=409,
                ) from None
        raise
    except AppException:
        _rollback_or_unknown(db)
        raise
    except Exception:
        _rollback_or_unknown(db)
        if committing:
            raise AppException(
                "Resource deletion outcome is unknown",
                code="RESOURCE_DELETE_OUTCOME_UNKNOWN",
                status_code=503,
            ) from None
        raise
