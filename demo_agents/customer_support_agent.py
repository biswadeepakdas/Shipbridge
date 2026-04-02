"""
Demo Customer Support AI Agent for ShipBridge Integration Testing
===================================================================

This agent demonstrates a production-ready customer support bot that:
- Uses OpenAI GPT-4 for conversation
- Integrates with ShipBridge's deployment, cost tracking, and governance APIs
- Tracks token usage and costs per conversation
- Logs all interactions for audit trails
- Can be deployed through ShipBridge's deployment pipeline

Usage:
    python demo_agents/customer_support_agent.py

Environment Variables Required:
    OPENAI_API_KEY - Your OpenAI API key
    SHIPBRIDGE_API_URL - ShipBridge API endpoint (default: http://localhost:8000)
    SHIPBRIDGE_API_KEY - ShipBridge API authentication token
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel


class Message(BaseModel):
    """Chat message."""

    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: datetime = datetime.now(timezone.utc)


class Conversation(BaseModel):
    """Conversation session."""

    id: str
    user_id: str
    messages: list[Message] = []
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    created_at: datetime = datetime.now(timezone.utc)


class CustomerSupportAgent:
    """Production-ready customer support agent with ShipBridge integration."""

    def __init__(
        self,
        openai_api_key: str,
        shipbridge_api_url: str = "http://localhost:8000",
        shipbridge_api_key: str | None = None,
    ):
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.shipbridge_url = shipbridge_api_url.rstrip("/")
        self.shipbridge_key = shipbridge_api_key
        self.model = "gpt-4"
        self.system_prompt = """You are a helpful customer support agent for TechCorp, a SaaS company.
Your role is to:
- Answer customer questions about our products and services
- Help troubleshoot technical issues
- Escalate complex issues to human agents when needed
- Maintain a friendly, professional tone

Available products:
- CloudSync Pro: File synchronization service ($9.99/month)
- DataVault: Secure backup solution ($19.99/month)
- TeamHub: Collaboration platform ($29.99/month per user)

Common issues and solutions:
- Login problems: Reset password at techcorp.com/reset
- Sync delays: Check internet connection and restart the app
- Billing questions: Contact billing@techcorp.com
"""

    async def _track_usage(
        self, conversation_id: str, tokens: int, cost_usd: float
    ) -> None:
        """Send usage metrics to ShipBridge for cost tracking."""
        if not self.shipbridge_key:
            return

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.shipbridge_url}/api/v1/costs/track",
                    headers={"Authorization": f"Bearer {self.shipbridge_key}"},
                    json={
                        "project_id": "demo-customer-support-agent",
                        "deployment_id": "production",
                        "conversation_id": conversation_id,
                        "model": self.model,
                        "tokens": tokens,
                        "cost_usd": cost_usd,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    timeout=5.0,
                )
        except Exception as e:
            print(f"⚠️  Failed to track usage in ShipBridge: {e}")

    async def _log_interaction(
        self, conversation_id: str, user_message: str, assistant_message: str
    ) -> None:
        """Send interaction logs to ShipBridge for governance audit trail."""
        if not self.shipbridge_key:
            return

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.shipbridge_url}/api/v1/governance/audit",
                    headers={"Authorization": f"Bearer {self.shipbridge_key}"},
                    json={
                        "project_id": "demo-customer-support-agent",
                        "event_type": "agent_interaction",
                        "conversation_id": conversation_id,
                        "user_message": user_message,
                        "assistant_message": assistant_message,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                    timeout=5.0,
                )
        except Exception as e:
            print(f"⚠️  Failed to log interaction in ShipBridge: {e}")

    async def chat(self, conversation: Conversation, user_message: str) -> str:
        """Process a user message and return the assistant's response."""
        # Add user message to conversation
        conversation.messages.append(
            Message(role="user", content=user_message, timestamp=datetime.now(timezone.utc))
        )

        # Build messages for OpenAI API
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(
            [{"role": m.role, "content": m.content} for m in conversation.messages]
        )

        # Call OpenAI API
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )

        assistant_message = response.choices[0].message.content or ""
        tokens_used = response.usage.total_tokens if response.usage else 0

        # Calculate cost (GPT-4 pricing: $0.03/1K prompt tokens, $0.06/1K completion tokens)
        # Simplified: using average of $0.045/1K tokens
        cost_usd = (tokens_used / 1000) * 0.045

        # Update conversation
        conversation.messages.append(
            Message(role="assistant", content=assistant_message, timestamp=datetime.now(timezone.utc))
        )
        conversation.total_tokens += tokens_used
        conversation.total_cost_usd += cost_usd

        # Track usage and log interaction in ShipBridge
        await self._track_usage(conversation.id, tokens_used, cost_usd)
        await self._log_interaction(conversation.id, user_message, assistant_message)

        return assistant_message

    async def register_with_shipbridge(self) -> dict[str, Any]:
        """Register this agent as a project in ShipBridge."""
        if not self.shipbridge_key:
            return {"error": "No ShipBridge API key provided"}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.shipbridge_url}/api/v1/projects",
                    headers={"Authorization": f"Bearer {self.shipbridge_key}"},
                    json={
                        "name": "Customer Support Agent (Demo)",
                        "framework": "openai",
                        "description": "Production-ready customer support bot for TechCorp",
                        "stack_json": {
                            "model": self.model,
                            "provider": "openai",
                            "features": ["chat", "context_memory", "cost_tracking"],
                            "integrations": ["shipbridge"],
                        },
                    },
                    timeout=10.0,
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            return {"error": str(e)}


async def interactive_demo():
    """Run an interactive demo of the customer support agent."""
    print("🤖 Customer Support Agent Demo")
    print("=" * 60)

    # Get credentials from environment
    openai_key = os.getenv("OPENAI_API_KEY")
    shipbridge_url = os.getenv("SHIPBRIDGE_API_URL", "http://localhost:8000")
    shipbridge_key = os.getenv("SHIPBRIDGE_API_KEY")

    if not openai_key:
        print("❌ OPENAI_API_KEY environment variable not set")
        return

    # Initialize agent
    agent = CustomerSupportAgent(
        openai_api_key=openai_key,
        shipbridge_api_url=shipbridge_url,
        shipbridge_api_key=shipbridge_key,
    )

    # Register with ShipBridge
    if shipbridge_key:
        print("\n📡 Registering agent with ShipBridge...")
        result = await agent.register_with_shipbridge()
        if "error" in result:
            print(f"⚠️  Registration failed: {result['error']}")
        else:
            print(f"✅ Registered as project: {result.get('id', 'unknown')}")
    else:
        print("\n⚠️  No SHIPBRIDGE_API_KEY set — running in standalone mode")

    # Start conversation
    conversation = Conversation(
        id=str(uuid.uuid4()),
        user_id="demo-user",
    )

    print(f"\n💬 Conversation ID: {conversation.id}")
    print("Type 'quit' to exit\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            response = await agent.chat(conversation, user_input)
            print(f"Agent: {response}\n")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Error: {e}\n")

    # Print summary
    print("\n" + "=" * 60)
    print(f"📊 Conversation Summary")
    print(f"   Messages: {len(conversation.messages)}")
    print(f"   Total tokens: {conversation.total_tokens:,}")
    print(f"   Total cost: ${conversation.total_cost_usd:.4f}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(interactive_demo())
