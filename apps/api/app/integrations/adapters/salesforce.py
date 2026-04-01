import time
from datetime import datetime, timezone
from typing import Any, Optional

from simple_salesforce import Salesforce, SalesforceError

from app.integrations.adapter import ConnectorAdapter, ConnectorHealthResult, NormalizedData
from app.config import get_settings

class SalesforceAdapter(ConnectorAdapter):
    """Connector for Salesforce CRM — opportunities, accounts, contacts, activities."""

    adapter_type = "salesforce"

    def __init__(self, instance_url: str = "", access_token: str = "") -> None:
        self.instance_url = instance_url
        self.access_token = access_token
        self.sf: Optional[Salesforce] = None

    async def _connect(self) -> None:
        settings = get_settings()
        if not self.sf:
            try:
                self.sf = Salesforce(
                    username=settings.salesforce_username,
                    password=settings.salesforce_password,
                    security_token=settings.salesforce_security_token,
                    instance_url=settings.salesforce_instance_url or self.instance_url,
                    session_id=self.access_token, # Use access_token as session_id if provided
                    # domain='test' if settings.environment == 'development' else 'login'
                )
            except SalesforceError as e:
                raise ConnectionError(f"Failed to connect to Salesforce: {e}") from e

    async def fetch(self, query: dict) -> dict[str, Any]:
        """Fetch data from Salesforce REST API using SOQL.

        Args:
            query: {"soql": "SELECT Id, Name FROM Opportunity LIMIT 10"}
        """
        await self._connect()
        if not self.sf: # Should not happen if _connect is successful
            raise ConnectionError("Salesforce connection not established.")

        soql_query = query.get("soql")
        if not soql_query:
            raise ValueError("SOQL query is required for Salesforce fetch.")

        try:
            result = self.sf.query(soql_query)
            # Extract object type from SOQL query for normalization
            object_type = "Unknown"
            if "FROM" in soql_query.upper():
                object_type = soql_query.upper().split("FROM")[1].strip().split(" ")[0]

            return {"totalSize": result["totalSize"], "records": result["records"], "objectType": object_type}
        except SalesforceError as e:
            raise RuntimeError(f"Salesforce query failed: {e}") from e

    async def health_check(self) -> ConnectorHealthResult:
        """Check Salesforce API connectivity."""
        start = time.monotonic()
        status = "unhealthy"
        error_message = None
        try:
            await self._connect()
            if self.sf:
                # Attempt a simple query to verify connectivity
                self.sf.query("SELECT Id FROM Account LIMIT 1")
                status = "healthy"
        except Exception as e:
            error_message = str(e)

        latency = (time.monotonic() - start) * 1000

        return ConnectorHealthResult(
            status=status,
            latency_ms=round(latency, 2),
            checked_at=datetime.now(timezone.utc).isoformat(),
            error_message=error_message
        )

    def normalize(self, raw_data: dict[str, Any]) -> NormalizedData:
        """Transform Salesforce API response into agent-friendly markdown."""
        obj_type = raw_data.get("objectType", "Unknown")
        records = raw_data.get("records", [])
        total = raw_data.get("totalSize", 0)

        lines = [f"# Salesforce {obj_type}s ({total} records)\n"]

        for record in records:
            # Remove attributes key which is Salesforce metadata
            record.pop("attributes", None)

            lines.append(f"## {record.get("Name", record.get("Subject", f"{obj_type} ID: {record.get("Id", "unknown")}"))}")
            for k, v in record.items():
                if k != "Id" and k != "Name" and k != "Subject": # Avoid duplicating Name/Subject
                    lines.append(f"- **{k}**: {v}")
            lines.append("")

        return NormalizedData(
            source="salesforce",
            data_type=obj_type.lower(),
            content="\n".join(lines),
            metadata={"total_records": total, "object_type": obj_type},
            fetched_at=datetime.now(timezone.utc).isoformat(),
        )
