"""Alembic environment.

The database URL is taken from application settings rather than from
``alembic.ini``, so migrations always run against the same database the
application is configured for. That removes a whole class of mistake where the
app and the migration tool disagree about which database they are talking to.

``target_metadata`` points at the ORM's declarative base, which is what makes
``alembic revision --autogenerate`` able to diff the models against the schema.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO_ROOT), str(REPO_ROOT / "apps" / "api")]

from argus_api.core.settings import get_settings  # noqa: E402
from argus_api.db.models import Base  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Settings resolve an empty DATABASE_URL to the local SQLite default, so this
# works on a fresh clone and against the Postgres service in docker-compose
# without any change here.
config.set_main_option("sqlalchemy.url", get_settings().database_url)


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting.

    Useful when a DBA has to review or apply the change themselves, which is
    the normal path in a regulated environment.
    """
    context.configure(
        url=get_settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against a live connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Detect column type changes, not just added and dropped columns.
            compare_type=True,
            # SQLite cannot ALTER most columns in place; batch mode rebuilds the
            # table instead, so the same migration works on both backends.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
