import stripe
from app.config import get_settings
import logging

logger = logging.getLogger(__name__)

class StripeMeteringService:
    def __init__(self):
        stripe.api_key = get_settings().stripe_api_key

    async def report_usage(self, customer_id: str, subscription_item_id: str, quantity: int, action: str = "increment"):
        if not get_settings().stripe_api_key:
            logger.warning("Stripe API key not configured. Skipping usage report.")
            return

        try:
            # In a real async app, use a threadpool or async stripe client
            stripe.SubscriptionItem.create_usage_record(
                subscription_item_id,
                quantity=quantity,
                timestamp="now",
                action=action,
            )
            logger.info(f"Reported {quantity} usage to Stripe for customer {customer_id}")
        except Exception as e:
            logger.error(f"Failed to report usage to Stripe: {e}")
