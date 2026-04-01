"""Tests for GitHub, Linear, Airtable, Google Workspace, Postgres adapters."""

import pytest

from app.integrations.adapters import ADAPTER_REGISTRY
from app.integrations.adapters.airtable import AirtableAdapter
from app.integrations.adapters.github_adapter import GitHubAdapter
from app.integrations.adapters.google_workspace import GoogleWorkspaceAdapter
from app.integrations.adapters.linear import LinearAdapter
from app.integrations.adapters.postgres_direct import PostgresDirectAdapter


# --- GitHub Adapter ---

class TestGitHubAdapter:
    @pytest.fixture
    def adapter(self) -> GitHubAdapter:
        return GitHubAdapter()

    @pytest.mark.asyncio
    async def test_fetch_issues(self, adapter: GitHubAdapter) -> None:
        result = await adapter.fetch({"object": "issues"})
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_pull_requests(self, adapter: GitHubAdapter) -> None:
        result = await adapter.fetch({"object": "pull_requests"})
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_commits(self, adapter: GitHubAdapter) -> None:
        result = await adapter.fetch({"object": "commits"})
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: GitHubAdapter) -> None:
        health = await adapter.health_check()
        assert health.status == "healthy"

    def test_normalize_issues(self, adapter: GitHubAdapter) -> None:
        raw = {"objectType": "issues", "items": [
            {"number": 42, "title": "Fix timeout", "state": "open",
             "labels": ["bug"], "assignee": "alice", "created_at": "2026-03-25"},
        ]}
        n = adapter.normalize(raw)
        assert "#42" in n.content
        assert "Fix timeout" in n.content
        assert "bug" in n.content

    def test_normalize_prs(self, adapter: GitHubAdapter) -> None:
        raw = {"objectType": "pull_requests", "items": [
            {"number": 15, "title": "feat: add connector", "state": "open",
             "author": "carol", "additions": 450, "deletions": 12, "changed_files": 8},
        ]}
        n = adapter.normalize(raw)
        assert "PR #15" in n.content
        assert "+450" in n.content

    def test_normalize_commits(self, adapter: GitHubAdapter) -> None:
        raw = {"objectType": "commits", "items": [
            {"sha": "abc1234567", "message": "Day 12 commit", "author": "dev"},
        ]}
        n = adapter.normalize(raw)
        assert "abc1234" in n.content
        assert "Day 12 commit" in n.content


# --- Linear Adapter ---

class TestLinearAdapter:
    @pytest.fixture
    def adapter(self) -> LinearAdapter:
        return LinearAdapter()

    @pytest.mark.asyncio
    async def test_fetch_issues(self, adapter: LinearAdapter) -> None:
        result = await adapter.fetch({"object": "issues"})
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_projects(self, adapter: LinearAdapter) -> None:
        result = await adapter.fetch({"object": "projects"})
        assert len(result["items"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_cycles(self, adapter: LinearAdapter) -> None:
        result = await adapter.fetch({"object": "cycles"})
        assert len(result["items"]) == 1

    def test_normalize_issues(self, adapter: LinearAdapter) -> None:
        raw = {"objectType": "issues", "items": [
            {"id": "LIN-101", "title": "Implement webhook", "state": "In Progress",
             "priority": 1, "assignee": "alice", "estimate": 3},
        ]}
        n = adapter.normalize(raw)
        assert "LIN-101" in n.content
        assert "Urgent" in n.content
        assert "3 pts" in n.content

    def test_normalize_projects(self, adapter: LinearAdapter) -> None:
        raw = {"objectType": "projects", "items": [
            {"name": "Integration OS", "progress": 0.65, "lead": "alice", "target_date": "2026-04-15"},
        ]}
        n = adapter.normalize(raw)
        assert "Integration OS" in n.content
        assert "65%" in n.content

    def test_normalize_cycles(self, adapter: LinearAdapter) -> None:
        raw = {"objectType": "cycles", "items": [
            {"name": "Sprint 12", "starts_at": "2026-03-25", "ends_at": "2026-04-07",
             "progress": 0.70, "completed_issues": 7, "total_issues": 10},
        ]}
        n = adapter.normalize(raw)
        assert "Sprint 12" in n.content
        assert "70%" in n.content
        assert "7/10" in n.content


# --- Airtable Adapter ---

class TestAirtableAdapter:
    @pytest.fixture
    def adapter(self) -> AirtableAdapter:
        return AirtableAdapter()

    @pytest.mark.asyncio
    async def test_fetch_records(self, adapter: AirtableAdapter) -> None:
        result = await adapter.fetch({"object": "records", "table": "Tasks"})
        assert len(result["records"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_tables(self, adapter: AirtableAdapter) -> None:
        result = await adapter.fetch({"object": "tables"})
        assert len(result["tables"]) == 2

    def test_normalize_records_as_table(self, adapter: AirtableAdapter) -> None:
        raw = {"objectType": "records", "table_name": "Tasks", "records": [
            {"id": "r1", "fields": {"Name": "Task A", "Status": "Done"}},
            {"id": "r2", "fields": {"Name": "Task B", "Status": "Todo"}},
        ]}
        n = adapter.normalize(raw)
        assert "Tasks" in n.content
        assert "Task A" in n.content
        assert "Task B" in n.content
        assert "| Name |" in n.content  # table header

    def test_normalize_tables(self, adapter: AirtableAdapter) -> None:
        raw = {"objectType": "tables", "tables": [
            {"id": "t1", "name": "Tasks", "fields": ["Name", "Status"]},
        ]}
        n = adapter.normalize(raw)
        assert "Tasks" in n.content
        assert "Name, Status" in n.content


# --- Google Workspace Adapter ---

class TestGoogleWorkspaceAdapter:
    @pytest.fixture
    def adapter(self) -> GoogleWorkspaceAdapter:
        return GoogleWorkspaceAdapter()

    @pytest.mark.asyncio
    async def test_fetch_drive_files(self, adapter: GoogleWorkspaceAdapter) -> None:
        result = await adapter.fetch({"object": "drive_files"})
        assert len(result["files"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_gmail_threads(self, adapter: GoogleWorkspaceAdapter) -> None:
        result = await adapter.fetch({"object": "gmail_threads"})
        assert len(result["threads"]) == 2

    def test_normalize_drive(self, adapter: GoogleWorkspaceAdapter) -> None:
        raw = {"objectType": "drive_files", "files": [
            {"id": "f1", "name": "Budget.xlsx", "mimeType": "spreadsheet",
             "modifiedTime": "2026-03-28", "owners": [{"displayName": "Alice"}], "size": "245000"},
        ]}
        n = adapter.normalize(raw)
        assert "Budget.xlsx" in n.content
        assert "Alice" in n.content
        assert "239 KB" in n.content

    def test_normalize_gmail(self, adapter: GoogleWorkspaceAdapter) -> None:
        raw = {"objectType": "gmail_threads", "threads": [
            {"id": "t1", "subject": "Deploy approval", "snippet": "Approved.",
             "messages_count": 4, "last_message_date": "2026-03-30"},
        ]}
        n = adapter.normalize(raw)
        assert "Deploy approval" in n.content
        assert "4" in n.content
        assert "Approved." in n.content


# --- Postgres Direct Adapter ---

class TestPostgresDirectAdapter:
    @pytest.fixture
    def adapter(self) -> PostgresDirectAdapter:
        return PostgresDirectAdapter()

    @pytest.mark.asyncio
    async def test_fetch_query(self, adapter: PostgresDirectAdapter) -> None:
        result = await adapter.fetch({"sql": "SELECT * FROM agents"})
        assert result["row_count"] == 3
        assert len(result["columns"]) == 4

    def test_normalize_query_result(self, adapter: PostgresDirectAdapter) -> None:
        raw = {"objectType": "query_result", "sql": "SELECT * FROM agents",
               "columns": ["id", "name"], "rows": [[1, "Alpha"], [2, "Beta"]],
               "row_count": 2, "execution_time_ms": 12.5}
        n = adapter.normalize(raw)
        assert "2 rows" in n.content
        assert "Alpha" in n.content
        assert "Beta" in n.content
        assert "| id | name |" in n.content
        assert "12.5ms" in n.content

    def test_normalize_empty_result(self, adapter: PostgresDirectAdapter) -> None:
        raw = {"objectType": "query_result", "sql": "SELECT 1",
               "columns": [], "rows": [], "row_count": 0, "execution_time_ms": 1.0}
        n = adapter.normalize(raw)
        assert "0 rows" in n.content


# --- Full Registry ---

class TestFullAdapterRegistry:
    def test_ten_adapters_registered(self) -> None:
        assert len(ADAPTER_REGISTRY) == 10
        expected = ["salesforce", "notion", "slack", "hubspot", "stripe",
                    "github", "linear", "airtable", "google_workspace", "postgres"]
        for name in expected:
            assert name in ADAPTER_REGISTRY, f"Missing adapter: {name}"
