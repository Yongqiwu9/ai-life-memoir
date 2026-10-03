# Alembic

Database schema changes are managed only through Alembic.

Typical workflow:

```bash
cd apps/backend

alembic revision --autogenerate -m "create users"
alembic upgrade head
alembic downgrade -1
```

Before `--autogenerate`, make sure all ORM models are imported into
`app/database/models_import.py`.

Never edit production PostgreSQL tables manually.
