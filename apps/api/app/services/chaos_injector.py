import asyncio
import random


class ChaosInjector:
    """Injects controlled failures and perturbations during canary stages."""

    async def inject_latency(self, min_ms: int = 100, max_ms: int = 2000):
        """Async sleep for a random duration to simulate latency spikes."""
        delay = random.uniform(min_ms, max_ms) / 1000.0
        await asyncio.sleep(delay)

    def inject_rate_limit_error(self):
        """Raises a RuntimeError simulating a 429 Too Many Requests response."""
        raise RuntimeError("429 Too Many Requests — rate limit simulated")

    def inject_context_corruption(self, chunks: list) -> list:
        """Randomly drops 30% of retrieved chunks to simulate context corruption."""
        if not chunks:
            return chunks
        num_to_keep = max(1, int(len(chunks) * 0.7))
        return random.sample(chunks, num_to_keep)

    def should_inject(self, probability: float = 0.1) -> bool:
        """Returns True with the given probability."""
        return random.random() < probability
