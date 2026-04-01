"""Temporal worker runner — connects to Temporal server, registers workflows + activities.

Start with: python -m app.workers
Or directly: python apps/api/app/workers/run_temporal.py
"""

import asyncio

import structlog

from app.config import get_settings

logger = structlog.get_logger()

TASK_QUEUE = "shipbridge-deployments"


async def run_worker() -> None:
    """Connect to Temporal and start the worker process."""
    from temporalio.client import Client
    from temporalio.worker import Worker

    from app.workers.temporal_workflows import (
        StagedDeploymentTemporalWorkflow,
        check_readiness_gate_activity,
        execute_stage_activity,
        rollback_activity,
    )

    settings = get_settings()
    logger.info(
        "temporal_worker_connecting",
        host=settings.temporal_host,
        namespace=settings.temporal_namespace,
    )

    client = await Client.connect(
        settings.temporal_host,
        namespace=settings.temporal_namespace,
    )

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[StagedDeploymentTemporalWorkflow],
        activities=[
            check_readiness_gate_activity,
            execute_stage_activity,
            rollback_activity,
        ],
    )

    logger.info("temporal_worker_running", task_queue=TASK_QUEUE)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
