"""Temporal worker entrypoint — registers workflows and activities."""

import asyncio
from temporalio.client import Client
from temporalio.worker import Worker

from app.config import get_settings
from app.workers.temporal_workflows import StagedDeploymentWorkflow, DeploymentActivities

async def run_worker():
    settings = get_settings()
    
    # Connect to Temporal
    client = await Client.connect(settings.temporal_url, namespace=settings.temporal_namespace)
    
    # Initialize activities
    activities = DeploymentActivities()
    
    # Run the worker
    worker = Worker(
        client,
        task_queue="deploy-queue",
        workflows=[StagedDeploymentWorkflow],
        activities=[
            activities.check_readiness_gate,
            activities.collect_real_metrics,
            activities.update_traffic_pct
        ],
    )
    
    print(f"Temporal worker starting on queue 'deploy-queue'...")
    await worker.run()

if __name__ == "__main__":
    asyncio.run(run_worker())
