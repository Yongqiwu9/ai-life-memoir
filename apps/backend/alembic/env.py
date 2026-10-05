import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.database import models_import  # noqa: F401
from app.database.base import Base
from test_support.database import resolve_migration_database_url

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _normal_database_url() -> str:
    from app.core.config import settings

    return settings.DATABASE_URL


test_migration_mode = os.environ.get("TEST_MIGRATION_MODE")
normal_database_url = "" if test_migration_mode == "1" else _normal_database_url()
migration_database_url = resolve_migration_database_url(
    normal_database_url, mode=test_migration_mode
)

# Normal migrations use Settings. Explicit test mode uses the guarded test URL.
# Escape percent signs so ConfigParser does not interpolate encoded characters.
config.set_main_option("sqlalchemy.url", migration_database_url.replace("%", "%%"))

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=migration_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
