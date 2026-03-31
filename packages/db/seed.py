"""Database seeding script — stub for Day 1, fixtures added on Day 3."""

import asyncio
import sys

import asyncpg


async def main() -> None:
    """Verify database connectivity and seed fixtures."""
    try:
        conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/shipbridge")
        version = await conn.fetchval("SELECT version()")
        await conn.close()
        print(f"Database connected: {version}")
        print("Seed complete. No fixtures to load yet.")
    except Exception as e:
        print(f"Database connection failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
