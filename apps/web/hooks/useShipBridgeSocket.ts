/**
 * useShipBridgeSocket — WebSocket hook for real-time updates from the ShipBridge backend.
 * Connects to ws://{host}/ws/{tenantId} and dispatches typed events.
 */

"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export type SocketEvent =
  | { type: "deployment_stage_update"; deployment_id: string; stage: string; status: string; metrics?: Record<string, number> }
  | { type: "rule_status_change"; rule_id: string; trigger: string; new_status: string }
  | { type: "assessment_complete"; project_id: string; score: number; status: string }
  | { type: "budget_alert"; project_id: string; spent: number; limit: number; pct: number };

type SocketEventHandler = (event: SocketEvent) => void;

interface UseShipBridgeSocketOptions {
  tenantId: string;
  onEvent?: SocketEventHandler;
  enabled?: boolean;
}

interface SocketState {
  connected: boolean;
  lastEvent: SocketEvent | null;
  error: string | null;
}

export function useShipBridgeSocket({
  tenantId,
  onEvent,
  enabled = true,
}: UseShipBridgeSocketOptions): SocketState {
  const [state, setState] = useState<SocketState>({
    connected: false,
    lastEvent: null,
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    if (!enabled || typeof window === "undefined") return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = process.env.NEXT_PUBLIC_API_HOST ?? window.location.hostname + ":8000";
    const url = `${protocol}//${host}/ws/${tenantId}`;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setState((prev) => ({ ...prev, connected: true, error: null }));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as SocketEvent;
          setState((prev) => ({ ...prev, lastEvent: data }));
          onEventRef.current?.(data);
        } catch {
          // Ignore malformed messages
        }
      };

      ws.onerror = () => {
        setState((prev) => ({ ...prev, error: "WebSocket connection error" }));
      };

      ws.onclose = () => {
        setState((prev) => ({ ...prev, connected: false }));
        wsRef.current = null;
        // Auto-reconnect after 3 seconds
        reconnectTimerRef.current = setTimeout(connect, 3000);
      };
    } catch (err) {
      setState((prev) => ({ ...prev, error: "Failed to create WebSocket" }));
    }
  }, [tenantId, enabled]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return state;
}
