"""Connector adapters — implementations of ConnectorAdapter for each service."""

from app.integrations.adapters.notion import NotionAdapter
from app.integrations.adapters.salesforce import SalesforceAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "salesforce": SalesforceAdapter,
    "notion": NotionAdapter,
}

__all__ = ["ADAPTER_REGISTRY", "NotionAdapter", "SalesforceAdapter"]
