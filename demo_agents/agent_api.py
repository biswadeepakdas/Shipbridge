"""
Customer Support Agent — FastAPI HTTP API
==========================================

Exposes the customer support agent as a REST API that ShipBridge can:
- Deploy and monitor
- Track costs via /api/v1/costs
- Audit interactions via /api/v1/governance/audit
- Run assessments against

Run:
    uvicorn demo_agents.agent_api:app --host 0.0.0.0 --port 8001 --reload

Endpoints:
    POST /chat          - Send a message to the agent
    GET  /conversations - List active conversations
    GET  /health        - Health check
    GET  /metrics       - Usage metrics (tokens, cost)
"""

import os
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from customer_support_agent import Conversation, CustomerSupportAgent

app = FastAPI(
    title="Customer Support Agent API",
    description="A production-ready customer support agent powered by GPT-4, integrated with ShipBridge.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation store (use Redis in production)
conversations: dict[str, Conversation] = {}

# Initialize agent
agent = CustomerSupportAgent(
    openai_api_key=os.getenv("OPENAI_API_KEY", ""),
    shipbridge_api_url=os.getenv("SHIPBRIDGE_API_URL", "http://localhost:8000"),
    shipbridge_api_key=os.getenv("SHIPBRIDGE_API_KEY"),
)


class ChatRequest(BaseModel):
    """Chat request payload."""
    message: str
    conversation_id: str | None = None
    user_id: str = "anonymous"


class ChatResponse(BaseModel):
    """Chat response payload."""
    conversation_id: str
    message: str
    tokens_used: int
    cost_usd: float
    timestamp: str


class MetricsResponse(BaseModel):
    """Usage metrics response."""
    total_conversations: int
    total_messages: int
    total_tokens: int
    total_cost_usd: float
    average_cost_per_conversation: float


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent": "customer-support-agent",
        "model": agent.model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Send a message to the customer support agent."""
    if not agent.client.api_key:
        raise HTTPException(status_code=503, detail="OpenAI API key not configured")

    # Get or create conversation
    if request.conversation_id and request.conversation_id in conversations:
        conversation = conversations[request.conversation_id]
    else:
        conversation = Conversation(
            id=str(uuid.uuid4()),
            user_id=request.user_id,
        )
        conversations[conversation.id] = conversation

    # Track tokens before
    tokens_before = conversation.total_tokens
    cost_before = conversation.total_cost_usd

    # Get response from agent
    response_message = await agent.chat(conversation, request.message)

    # Calculate this turn's usage
    tokens_this_turn = conversation.total_tokens - tokens_before
    cost_this_turn = conversation.total_cost_usd - cost_before

    return ChatResponse(
        conversation_id=conversation.id,
        message=response_message,
        tokens_used=tokens_this_turn,
        cost_usd=cost_this_turn,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/conversations")
async def list_conversations():
    """List all active conversations with summary stats."""
    return {
        "conversations": [
            {
                "id": c.id,
                "user_id": c.user_id,
                "message_count": len(c.messages),
                "total_tokens": c.total_tokens,
                "total_cost_usd": c.total_cost_usd,
                "created_at": c.created_at.isoformat(),
            }
            for c in conversations.values()
        ]
    }


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get a specific conversation with full message history."""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    c = conversations[conversation_id]
    return {
        "id": c.id,
        "user_id": c.user_id,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp.isoformat(),
            }
            for m in c.messages
        ],
        "total_tokens": c.total_tokens,
        "total_cost_usd": c.total_cost_usd,
        "created_at": c.created_at.isoformat(),
    }


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics():
    """Get aggregated usage metrics across all conversations."""
    total_conversations = len(conversations)
    total_messages = sum(len(c.messages) for c in conversations.values())
    total_tokens = sum(c.total_tokens for c in conversations.values())
    total_cost = sum(c.total_cost_usd for c in conversations.values())
    avg_cost = total_cost / total_conversations if total_conversations > 0 else 0.0

    return MetricsResponse(
        total_conversations=total_conversations,
        total_messages=total_messages,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        average_cost_per_conversation=avg_cost,
    )
