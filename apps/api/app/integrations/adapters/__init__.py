"""Connector adapters — implementations of ConnectorAdapter for each service."""

from app.integrations.adapters.hubspot import HubSpotAdapter
from app.integrations.adapters.notion import NotionAdapter
from app.integrations.adapters.salesforce import SalesforceAdapter
from app.integrations.adapters.slack import SlackAdapter
from app.integrations.adapters.stripe import StripeAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "salesforce": SalesforceAdapter,
    "notion": NotionAdapter,
    "slack": SlackAdapter,
    "hubspot": HubSpotAdapter,
    "stripe": StripeAdapter,
}

__all__ = [
    "ADAPTER_REGISTRY",
    "HubSpotAdapter",
    "NotionAdapter",
    "SalesforceAdapter",
    "SlackAdapter",
    "StripeAdapter",
]
