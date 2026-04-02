from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine

from alembic import context

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model\"s MetaData object here
# for \"autogenerate\" support
from app.db import Base  # Import your Base from app.db

# Import all models to ensure they are registered with SQLAlchemy Base.metadata
# This needs to happen AFTER Base is defined to avoid circular imports
import app.models.auth
import app.models.connectors
import app.models.deployments
import app.models.embeddings
import app.models.evals
import app.models.events
import app.models.projects

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in \"offline\" mode.\n\n    This configures the context with just a URL\n    and not an Engine, though an Engine is acceptable\n    here as well.  By skipping the Engine creation\n    we don\"t even need a DBAPI to be available.\n\n    Calls to context.execute() here emit the given string to the\n    script output.\n\n    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations in \"online\" mode.\n\n    In this scenario we need to create an Engine\n    and associate a connection with the context.\n\n    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True, # Use future=True for async support
    )
    # Wrap the connectable in AsyncEngine
    async_connectable = AsyncEngine(connectable)

    async with async_connectable.connect() as connection:
        await connection.run_sync(lambda sync_connection: (
            context.configure(
                connection=sync_connection, target_metadata=target_metadata, dialect_name="postgresql+asyncpg"
            ),
            context.run_migrations()
        ))


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio
    asyncio.run(run_migrations_online())
