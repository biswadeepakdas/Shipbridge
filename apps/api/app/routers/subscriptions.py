"""Subscription CRUD routes — manage event subscriptions for agent triggers."""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.middleware.auth import AuthContext, get_auth_context
from app.os_layer.subscription_engine import (
    Subscription,
    SubscriptionEngine,
    SubscriptionMatchResult,
    subscription_engine,
)
from app.schemas.response import APIResponse

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


class SubscriptionCreate(BaseModel):
    """Request to create a subscription."""

    name: str
    event_type: str
    filter_expression: str | None = None
    agent_id: str
    debounce_seconds: int = 0


class SubscriptionOut(BaseModel):
    """Subscription response."""

    id: str
    name: str
    event_type: str
    filter_expression: str | None
    agent_id: str
    debounce_seconds: int
    is_active: bool


class TestMatchRequest(BaseModel):
    """Request to test-match an event against subscriptions."""

    event_type: str
    payload: dict


@router.post("", response_model=APIResponse[SubscriptionOut])
async def create_subscription(
    body: SubscriptionCreate,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[SubscriptionOut]:
    """Create a new event subscription."""
    sub = Subscription(
        id=str(uuid.uuid4()),
        tenant_id=auth.tenant_id,
        name=body.name,
        event_type=body.event_type,
        filter_expression=body.filter_expression,
        agent_id=body.agent_id,
        debounce_seconds=body.debounce_seconds,
    )
    subscription_engine.register(sub)
    return APIResponse(data=SubscriptionOut(
        id=sub.id, name=sub.name, event_type=sub.event_type,
        filter_expression=sub.filter_expression, agent_id=sub.agent_id,
        debounce_seconds=sub.debounce_seconds, is_active=sub.is_active,
    ))


@router.get("", response_model=APIResponse[list[SubscriptionOut]])
async def list_subscriptions(
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[list[SubscriptionOut]]:
    """List active subscriptions for the authenticated tenant."""
    subs = subscription_engine.list_subscriptions(auth.tenant_id)
    return APIResponse(data=[
        SubscriptionOut(
            id=s.id, name=s.name, event_type=s.event_type,
            filter_expression=s.filter_expression, agent_id=s.agent_id,
            debounce_seconds=s.debounce_seconds, is_active=s.is_active,
        )
        for s in subs
    ])


@router.delete("/{subscription_id}", response_model=APIResponse[dict])
async def delete_subscription(
    subscription_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[dict]:
    """Delete a subscription."""
    removed = subscription_engine.remove(subscription_id)
    if not removed:
        from app.exceptions import AppError, ErrorCode
        raise AppError(ErrorCode.NOT_FOUND, f"Subscription {subscription_id} not found")
    return APIResponse(data={"deleted": subscription_id})


@router.post("/test-match", response_model=APIResponse[SubscriptionMatchResult])
async def test_match(
    body: TestMatchRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> APIResponse[SubscriptionMatchResult]:
    """Test-match an event against current subscriptions without triggering agents."""
    result = subscription_engine.match_event(
        event_type=body.event_type,
        payload=body.payload,
        tenant_id=auth.tenant_id,
    )
    return APIResponse(data=result)
