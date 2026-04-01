import httpx
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class BetterstackService:
    def __init__(self):
        self.heartbeat_url = settings.betterstack_heartbeat_url

    async def send_heartbeat(self):
        if not self.heartbeat_url:
            logger.warning("Betterstack heartbeat URL not configured. Skipping heartbeat.")
            return

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(self.heartbeat_url)
                response.raise_for_status()
                logger.info("Sent heartbeat to Betterstack")
        except Exception as e:
            logger.error(f"Failed to send heartbeat to Betterstack: {e}")
