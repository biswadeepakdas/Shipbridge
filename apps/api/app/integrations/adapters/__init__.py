"""Connector adapters — 10 implementations of ConnectorAdapter."""

from app.integrations.adapters.airtable import AirtableAdapter
from app.integrations.adapters.github_adapter import GitHubAdapter
from app.integrations.adapters.google_workspace import GoogleWorkspaceAdapter
from app.integrations.adapters.hubspot import HubSpotAdapter
from app.integrations.adapters.linear import LinearAdapter
from app.integrations.adapters.notion import NotionAdapter
from app.integrations.adapters.postgres_direct import PostgresDirectAdapter
from app.integrations.adapters.salesforce import SalesforceAdapter
from app.integrations.adapters.slack import SlackAdapter
from app.integrations.adapters.stripe import StripeAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "salesforce": SalesforceAdapter,
    "notion": NotionAdapter,
    "slack": SlackAdapter,
    "hubspot": HubSpotAdapter,
    "stripe": StripeAdapter,
    "github": GitHubAdapter,
    "linear": LinearAdapter,
    "airtable": AirtableAdapter,
    "google_workspace": GoogleWorkspaceAdapter,
    "postgres": PostgresDirectAdapter,
}

__all__ = [
    "ADAPTER_REGISTRY",
    "AirtableAdapter",
    "GitHubAdapter",
    "GoogleWorkspaceAdapter",
    "HubSpotAdapter",
    "LinearAdapter",
    "NotionAdapter",
    "PostgresDirectAdapter",
    "SalesforceAdapter",
    "SlackAdapter",
    "StripeAdapter",
]
