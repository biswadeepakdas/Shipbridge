from app.integrations.adapters.base import ConnectorAdapter
import httpx

class LinearAdapter(ConnectorAdapter):
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.linear.app/graphql"
        self.headers = {"Authorization": self.api_key, "Content-Type": "application/json"}

    async def fetch_data(self, query: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(self.base_url, headers=self.headers, json={"query": query})
            response.raise_for_status()
            return response.json()

    async def normalize(self, raw_data: dict) -> dict:
        return {"normalized": True, "data": raw_data}
