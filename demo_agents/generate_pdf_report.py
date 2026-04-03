"""Generate compliance PDF report for a specific agent project."""

import asyncio
import os
import sys

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["JWT_SECRET"] = "test-secret-for-demo"
os.environ["ENVIRONMENT"] = "development"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


async def main():
    from app.db import Base, get_db
    from app.main import app as fastapi_app

    test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    TestSession = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    import app.models  # noqa: F401

    # Filter tables with unsupported types
    tables = [t for t in Base.metadata.sorted_tables
              if not any("TSVECTOR" in str(c.type).upper() or "VECTOR" in str(c.type).upper() for c in t.columns)]

    async with test_engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))

    async def override_db() -> AsyncGenerator[AsyncSession, None]:
        async with TestSession() as session:
            yield session

    fastapi_app.dependency_overrides[get_db] = override_db

    from app.middleware.rate_limit import rate_limiter
    rate_limiter.reset()

    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Signup
        resp = await client.post("/api/v1/auth/signup", json={
            "email": "demo@shipbridge.dev",
            "full_name": "Demo User",
            "tenant_name": "Demo Workspace",
            "tenant_slug": "demo-workspace",
        })
        auth = resp.json().get("data", {})
        token = auth.get("token", {}).get("access_token", "")
        headers = {"Authorization": f"Bearer {token}"}

        # Create AutoGPT project
        print("Creating AutoGPT project...")
        resp = await client.post("/api/v1/projects", json={
            "name": "AutoGPT Autonomous Agent",
            "framework": "custom",
            "description": "Autonomous continuous agent for content, research, and data analysis.",
            "repo_url": "https://github.com/Significant-Gravitas/AutoGPT",
            "stack_json": {
                "models": ["gpt-4o"],
                "tools": ["web_browser", "file_manager", "code_executor", "search_engine"],
                "deployment": "docker",
                "user_input": True,
                "mcp_endpoints": ["/tools/browser", "/tools/files", "/tools/code"],
                "test_coverage": 20,
            },
        }, headers=headers)
        project = resp.json().get("data", {})
        project_id = project.get("id")
        print(f"Project: {project_id}")

        # Run assessment
        print("Running assessment...")
        resp = await client.post(f"/api/v1/projects/{project_id}/assess", headers=headers)
        assessment = resp.json().get("data", {})
        print(f"Score: {assessment.get('total_score')}/100")

        # Generate PDF
        print("Generating compliance PDF...")
        resp = await client.get(f"/api/v1/governance/pdf/{project_id}/download", headers=headers)

        if resp.status_code == 200:
            pdf_path = "/home/user/Shipbridge/autogpt_compliance_report.pdf"
            with open(pdf_path, "wb") as f:
                f.write(resp.content)
            print(f"\n✅ PDF saved to: {pdf_path}")
            print(f"   Size: {len(resp.content):,} bytes")
        else:
            print(f"❌ PDF generation failed: {resp.status_code}")
            print(f"   Response: {resp.text[:500]}")

    await engine_cleanup(test_engine)


async def engine_cleanup(engine):
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
