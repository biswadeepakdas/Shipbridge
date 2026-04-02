"""Tests for Salesforce and Notion adapters — fetch, health_check, normalize."""

import pytest

from app.integrations.adapters.salesforce import SalesforceAdapter
from app.integrations.adapters.notion import NotionAdapter


# --- Salesforce Adapter ---

class TestSalesforceAdapter:
    @pytest.fixture
    def adapter(self) -> SalesforceAdapter:
        return SalesforceAdapter(instance_url="https://test.salesforce.com")

    @pytest.mark.asyncio
    async def test_fetch_opportunities(self, adapter: SalesforceAdapter) -> None:
        result = await adapter.fetch({"object": "Opportunity"})
        assert result["totalSize"] == 2
        assert result["objectType"] == "Opportunity"
        assert len(result["records"]) == 2

    @pytest.mark.asyncio
    async def test_fetch_accounts(self, adapter: SalesforceAdapter) -> None:
        result = await adapter.fetch({"object": "Account"})
        assert result["totalSize"] == 2
        assert result["records"][0]["Name"] == "Acme Corp"

    @pytest.mark.asyncio
    async def test_fetch_contacts(self, adapter: SalesforceAdapter) -> None:
        result = await adapter.fetch({"object": "Contact"})
        assert result["totalSize"] == 1

    @pytest.mark.asyncio
    async def test_fetch_activities(self, adapter: SalesforceAdapter) -> None:
        result = await adapter.fetch({"object": "Activity"})
        assert result["totalSize"] == 1

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: SalesforceAdapter) -> None:
        health = await adapter.health_check()
        assert health.status == "healthy"
        assert health.latency_ms > 0

    def test_normalize_opportunities(self, adapter: SalesforceAdapter) -> None:
        raw = {
            "totalSize": 2,
            "objectType": "Opportunity",
            "records": [
                {"Id": "001", "Name": "Acme Deal", "Amount": 125000,
                 "StageName": "Closed Won", "CloseDate": "2026-03-15"},
                {"Id": "002", "Name": "Beta Deal", "Amount": 45000,
                 "StageName": "Negotiation", "CloseDate": "2026-04-30"},
            ],
        }
        normalized = adapter.normalize(raw)
        assert normalized.source == "salesforce"
        assert normalized.data_type == "opportunity"
        assert "Acme Deal" in normalized.content
        assert "$125,000" in normalized.content
        assert "Closed Won" in normalized.content
        assert "Beta Deal" in normalized.content
        assert normalized.metadata["total_records"] == 2

    def test_normalize_accounts(self, adapter: SalesforceAdapter) -> None:
        raw = {
            "totalSize": 1,
            "objectType": "Account",
            "records": [
                {"Id": "001", "Name": "Acme Corp", "Industry": "Technology",
                 "AnnualRevenue": 5000000, "NumberOfEmployees": 250},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Acme Corp" in normalized.content
        assert "Technology" in normalized.content
        assert "$5,000,000" in normalized.content

    def test_normalize_contacts(self, adapter: SalesforceAdapter) -> None:
        raw = {
            "totalSize": 1,
            "objectType": "Contact",
            "records": [
                {"Id": "001", "FirstName": "Alice", "LastName": "Johnson",
                 "Email": "alice@acme.com", "Title": "VP Engineering"},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Alice Johnson" in normalized.content
        assert "VP Engineering" in normalized.content

    def test_normalize_empty_records(self, adapter: SalesforceAdapter) -> None:
        raw = {"totalSize": 0, "objectType": "Opportunity", "records": []}
        normalized = adapter.normalize(raw)
        assert "0 records" in normalized.content
        assert normalized.metadata["total_records"] == 0


# --- Notion Adapter ---

class TestNotionAdapter:
    @pytest.fixture
    def adapter(self) -> NotionAdapter:
        return NotionAdapter(access_token="ntn_test")

    @pytest.mark.asyncio
    async def test_fetch_page(self, adapter: NotionAdapter) -> None:
        result = await adapter.fetch({"type": "page"})
        assert result["object"] == "page"
        assert result["id"] == "page-001"

    @pytest.mark.asyncio
    async def test_fetch_database(self, adapter: NotionAdapter) -> None:
        result = await adapter.fetch({"type": "database"})
        assert result["object"] == "database"
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_fetch_search(self, adapter: NotionAdapter) -> None:
        result = await adapter.fetch({"type": "search"})
        assert result["object"] == "list"
        assert len(result["results"]) == 3

    @pytest.mark.asyncio
    async def test_health_check(self, adapter: NotionAdapter) -> None:
        health = await adapter.health_check()
        assert health.status == "healthy"
        assert health.latency_ms > 0

    def test_normalize_page(self, adapter: NotionAdapter) -> None:
        raw = {
            "object": "page",
            "id": "page-001",
            "properties": {
                "title": {"title": [{"plain_text": "Q4 Planning"}]},
                "Status": {"select": {"name": "In Progress"}},
                "Priority": {"select": {"name": "High"}},
            },
            "created_time": "2026-03-01T10:00:00Z",
            "last_edited_time": "2026-03-28T14:30:00Z",
        }
        normalized = adapter.normalize(raw)
        assert normalized.source == "notion"
        assert normalized.data_type == "page"
        assert "Q4 Planning" in normalized.content
        assert "In Progress" in normalized.content
        assert "High" in normalized.content

    def test_normalize_database(self, adapter: NotionAdapter) -> None:
        raw = {
            "object": "database",
            "id": "db-001",
            "title": [{"plain_text": "Product Roadmap"}],
            "results": [
                {"id": "row-1", "properties": {
                    "Name": {"title": [{"plain_text": "Feature A"}]},
                    "Status": {"select": {"name": "Done"}},
                }},
                {"id": "row-2", "properties": {
                    "Name": {"title": [{"plain_text": "Feature B"}]},
                    "Status": {"select": {"name": "In Progress"}},
                }},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Product Roadmap" in normalized.content
        assert "Feature A" in normalized.content
        assert "Feature B" in normalized.content
        assert "Done" in normalized.content
        assert normalized.metadata["row_count"] == 2

    def test_normalize_search(self, adapter: NotionAdapter) -> None:
        raw = {
            "object": "list",
            "results": [
                {"object": "page", "id": "p1",
                 "properties": {"title": {"title": [{"plain_text": "Meeting Notes"}]}}},
                {"object": "database", "id": "d1",
                 "title": [{"plain_text": "Task Board"}]},
            ],
        }
        normalized = adapter.normalize(raw)
        assert "Meeting Notes" in normalized.content
        assert "Task Board" in normalized.content
        assert normalized.metadata["result_count"] == 2

    def test_normalize_empty_database(self, adapter: NotionAdapter) -> None:
        raw = {"object": "database", "id": "db-empty", "title": [{"plain_text": "Empty DB"}], "results": []}
        normalized = adapter.normalize(raw)
        assert "0 rows" in normalized.content

    def test_extract_property_select(self, adapter: NotionAdapter) -> None:
        assert NotionAdapter._extract_property_value({"select": {"name": "Active"}}) == "Active"

    def test_extract_property_people(self, adapter: NotionAdapter) -> None:
        assert NotionAdapter._extract_property_value({"people": [{"name": "Alice"}]}) == "Alice"

    def test_extract_property_empty(self, adapter: NotionAdapter) -> None:
        assert NotionAdapter._extract_property_value({}) == ""
