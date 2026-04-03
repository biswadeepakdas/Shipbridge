"""Drop all tables — DEVELOPMENT ONLY.

Refuses to run if ENVIRONMENT is set to 'production' or 'staging'.
"""

import asyncio
import os
import sys


async def drop_all_tables():
    env = os.getenv("ENVIRONMENT", "development")
    if env in ("production", "staging"):
        print(f"ABORT: drop_tables.py cannot run in '{env}' environment.", file=sys.stderr)
        sys.exit(1)

    confirm = input(f"This will DROP ALL TABLES in the '{env}' database. Type 'yes' to confirm: ")
    if confirm.strip().lower() != "yes":
        print("Aborted.")
        sys.exit(0)

    from app.db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("All tables dropped.")


if __name__ == "__main__":
    asyncio.run(drop_all_tables())
