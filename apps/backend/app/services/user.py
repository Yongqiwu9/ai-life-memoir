from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.core.security import create_access_token, hash_password, verify_password
from app.crud import user as user_crud
from app.models.user import User


class EmailAlreadyRegisteredError(AppException):
    def __init__(self) -> None:
        super().__init__(
            "Email already registered",
            code="EMAIL_ALREADY_REGISTERED",
            status_code=409,
        )


class InvalidCredentialsError(AppException):
    def __init__(self) -> None:
        super().__init__(
            "Invalid email or password",
            code="INVALID_CREDENTIALS",
            status_code=401,
        )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def register_user(db: Session, *, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    if user_crud.get_user_by_email(db, normalized_email) is not None:
        raise EmailAlreadyRegisteredError()
    return user_crud.create_user(
        db,
        email=normalized_email,
        password_hash=hash_password(password),
    )


def authenticate_user(db: Session, *, email: str, password: str) -> User:
    normalized_email = _normalize_email(email)
    user = user_crud.get_user_by_email(db, normalized_email)
    if (
        user is None
        or user.principal_kind != "account"
        or not user.is_active
        or not user.password_hash
        or not verify_password(password, user.password_hash)
    ):
        raise InvalidCredentialsError()
    return user


def login_user(db: Session, *, email: str, password: str) -> str:
    user = authenticate_user(db, email=email, password=password)
    return create_access_token(subject=str(user.id), auth_generation=user.auth_generation)
