from app.integrations.adapters.base import ConnectorAdapter
import stripe

class StripeAdapter(ConnectorAdapter):
    def __init__(self, api_key: str):
        stripe.api_key = api_key

    async def fetch_data(self, customer_id: str) -> dict:
        # In a real async app, use a threadpool or async stripe client if available
        customer = stripe.Customer.retrieve(customer_id)
        return customer

    async def normalize(self, raw_data: dict) -> dict:
        return {"normalized": True, "data": raw_data}
