import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_webhook_to_deployment_pipeline():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # 1. Simulate webhook ingestion
        webhook_payload = {
            "type": "issue_completed",
            "team_id": "team-01",
            "priority": "urgent",
            "issue_id": "LIN-42"
        }
        response = await ac.post("/api/v1/webhooks/linear", json=webhook_payload)
        assert response.status_code == 202
        assert response.json()["status"] == "accepted"

        # 2. Simulate rule generation (mocked for test)
        # In a real e2e test, we would wait for the background worker to process the event
        # and generate a rule, then we would approve it via the HITL gate.
        
        # 3. Simulate deployment trigger
        deployment_payload = {
            "project_id": "test-project",
            "trigger_event": "linear.issue_completed"
        }
        response = await ac.post("/api/v1/deployments/trigger", json=deployment_payload)
        assert response.status_code == 202
        assert "workflow_id" in response.json()

        # 4. Check deployment status
        workflow_id = response.json()["workflow_id"]
        response = await ac.get(f"/api/v1/deployments/{workflow_id}/status")
        assert response.status_code == 200
        assert response.json()["status"] in ["RUNNING", "COMPLETED"]
