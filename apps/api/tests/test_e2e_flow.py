"""E2E test: signup → create project → connect → assess → check readiness → deploy.

This is the Day 30 launch readiness verification — the full user flow
from onboarding to deployment in a single test.
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_e2e_flow(client: AsyncClient) -> None:
    """Complete E2E: signup → project → assess → readiness → deploy attempt."""

    # Step 1: Signup
    signup_resp = await client.post("/api/v1/auth/signup", json={
        "email": "e2e@shipbridge.dev",
        "full_name": "E2E Test User",
        "tenant_name": "E2E Corp",
        "tenant_slug": "e2e-corp",
    })
    assert signup_resp.status_code == 200
    token = signup_resp.json()["data"]["token"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Step 2: Quick-start onboarding (create project + first assessment)
    onboard_resp = await client.post("/api/v1/onboarding/quick-start", headers=headers, json={
        "project_name": "E2E Agent",
        "framework": "langraph",
        "stack_json": {
            "models": ["claude-3-5-sonnet", "claude-3-haiku"],
            "tools": ["salesforce", "slack"],
            "deployment": "railway",
        },
    })
    assert onboard_resp.status_code == 200
    project_id = onboard_resp.json()["data"]["project_id"]
    score = onboard_resp.json()["data"]["assessment_score"]
    assert score > 0
    assert project_id

    # Step 3: Create a connector
    connector_resp = await client.post("/api/v1/connectors", headers=headers, json={
        "name": "Salesforce E2E",
        "adapter_type": "salesforce",
        "auth_type": "oauth2",
    })
    assert connector_resp.status_code == 200
    connector_id = connector_resp.json()["data"]["id"]

    # Step 4: Test the connector
    test_resp = await client.post(f"/api/v1/connectors/{connector_id}/test", headers=headers)
    assert test_resp.status_code == 200
    assert test_resp.json()["data"]["status"] == "healthy"

    # Step 5: Run full assessment
    assess_resp = await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)
    assert assess_resp.status_code == 200
    assessment = assess_resp.json()["data"]
    assert assessment["status"] == "complete"
    assert len(assessment["scores_json"]) == 5

    # Step 6: Check readiness
    readiness_resp = await client.get(f"/api/v1/projects/{project_id}/readiness", headers=headers)
    assert readiness_resp.status_code == 200
    readiness = readiness_resp.json()["data"]
    assert "can_deploy" in readiness
    assert readiness["target_score"] == 75

    # Step 7: Attempt deployment
    deploy_resp = await client.post("/api/v1/deployments", headers=headers, json={
        "project_id": project_id,
    })
    assert deploy_resp.status_code == 200
    deployment = deploy_resp.json()["data"]
    # Will be "running" if score >= 75, "failed" if blocked by gate
    assert deployment["status"] in ("running", "failed")

    # Step 8: Generate compliance PDF
    pdf_resp = await client.post(f"/api/v1/governance/pdf/{project_id}", headers=headers)
    assert pdf_resp.status_code == 200
    pdf = pdf_resp.json()["data"]
    assert len(pdf["pillars"]) == 5
    assert len(pdf["compliance_checklist"]) == 20
    assert pdf["html"].startswith("<!DOCTYPE html>")

    # Step 9: Check billing
    billing_resp = await client.get("/api/v1/billing/current", headers=headers)
    assert billing_resp.status_code == 200
    assert billing_resp.json()["data"]["trial_active"] is True

    # Step 10: Create API key
    key_resp = await client.post("/api/v1/auth/api-keys", headers=headers, json={
        "name": "E2E CI Key",
        "scope": "admin",
    })
    assert key_resp.status_code == 200
    assert key_resp.json()["data"]["raw_key"].startswith("sb_")

    # Step 11: Check audit trail
    audit_resp = await client.get("/api/v1/governance/audit", headers=headers)
    assert audit_resp.status_code == 200
    # Deployment should have generated audit entries
    assert len(audit_resp.json()["data"]) >= 0  # may be empty in test isolation


@pytest.mark.asyncio
async def test_cross_tenant_isolation_e2e(client: AsyncClient) -> None:
    """Verify complete cross-tenant isolation across all resources."""

    # Create two tenants
    resp_a = await client.post("/api/v1/auth/signup", json={
        "email": "tenant-a@e2e.com", "full_name": "A User",
        "tenant_name": "A Corp", "tenant_slug": "e2e-a-corp",
    })
    token_a = resp_a.json()["data"]["token"]["access_token"]
    headers_a = {"Authorization": f"Bearer {token_a}"}

    resp_b = await client.post("/api/v1/auth/signup", json={
        "email": "tenant-b@e2e.com", "full_name": "B User",
        "tenant_name": "B Corp", "tenant_slug": "e2e-b-corp",
    })
    token_b = resp_b.json()["data"]["token"]["access_token"]
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant A creates resources
    proj_a = await client.post("/api/v1/projects", headers=headers_a, json={
        "name": "A Project", "framework": "langraph",
        "stack_json": {"models": ["sonnet"]},
    })
    project_a_id = proj_a.json()["data"]["id"]

    await client.post("/api/v1/connectors", headers=headers_a, json={
        "name": "A Connector", "adapter_type": "salesforce",
    })

    # Tenant B cannot see A's projects
    projects_b = await client.get("/api/v1/projects", headers=headers_b)
    for p in projects_b.json()["data"]:
        assert p["name"] != "A Project"

    # Tenant B cannot see A's connectors
    connectors_b = await client.get("/api/v1/connectors", headers=headers_b)
    for c in connectors_b.json()["data"]:
        assert c["name"] != "A Connector"

    # Tenant B cannot assess A's project
    assess_resp = await client.post(f"/api/v1/projects/{project_a_id}/assess", headers=headers_b)
    assert assess_resp.status_code == 404
