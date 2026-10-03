# Backend AGENTS

## Scope
This directory contains the production FastAPI backend.

## Rules
- Python 3.12+
- FastAPI + SQLAlchemy 2.x + Pydantic v2 + Alembic
- PostgreSQL is the primary database.
- Use timezone-aware UTC timestamps.
- ORM models use SQLAlchemy 2.x typed mappings.
- API flow: Router -> Service -> CRUD -> Model.
- Schemas define API input/output; do not expose ORM objects directly.
- Authentication must use JWT in production.
- Never trust `user_id` from request payload for ownership decisions.
- Enforce owner/family isolation in the service/query layer.
- Database schema changes must go through Alembic.
- Keep transactions explicit for multi-write operations.
- Do not put business logic in routers.
- Do not import templates into runtime code.
- Add tests for authentication, CRUD behavior, validation, and cross-user isolation.

## Configuration
Runtime configuration comes from environment variables via `app/core/config.py`.
Do not hard-code credentials or production secrets.
