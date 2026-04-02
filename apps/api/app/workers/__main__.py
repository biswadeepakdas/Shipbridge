"""Allow `python -m app.workers` to start the Temporal worker."""

import asyncio

from app.workers.run_temporal import run_worker

asyncio.run(run_worker())
