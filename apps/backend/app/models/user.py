import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.family import Family


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "principal_kind IN ('account', 'rights_only', 'system')", name="ck_users_principal_kind"
        ),
        CheckConstraint("auth_generation > 0", name="ck_users_auth_generation"),
        CheckConstraint(
            "(principal_kind = 'account' AND email IS NOT NULL AND length(trim(email)) > 3 "
            "AND email LIKE '%@%' AND password_hash IS NOT NULL AND length(password_hash) > 0) "
            "OR (principal_kind IN ('rights_only', 'system') AND email IS NULL AND password_hash IS NULL)",
            name="ck_users_credentials",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    principal_kind: Mapped[str] = mapped_column(
        String(32), default="account", server_default="account", nullable=False
    )
    auth_generation: Mapped[int] = mapped_column(
        BigInteger, default=1, server_default="1", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    families: Mapped[list["Family"]] = relationship(back_populates="owner")
