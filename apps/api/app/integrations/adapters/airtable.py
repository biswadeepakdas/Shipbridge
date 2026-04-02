from app.integrations.adapters.base import ConnectorAdapter
import httpx

class AirtableAdapter(ConnectorAdapter):
    def __init__(self, api_key: str, base_id: str):
        self.api_key = api_key
        self.base_id = base_id
        self.base_url = f"https://api.airtable.com/v0/{self.base_id}"
        self.headers = {"Authorization": f"Bearer {self.api_key}"}

    async def fetch_data(self, table_name: str) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/{table_name}", headers=self.headers)
            response.raise_for_status()
            return response.json()

    async def normalize(self, raw_data: dict) -> dict:
        return {"normalized": True, "data": raw_data}
