"""
Import every ORM model here so Alembic can discover metadata.
"""

from app.models.family import Family  # noqa: F401
from app.models.family_member import FamilyMember  # noqa: F401
from app.models.user import User  # noqa: F401
