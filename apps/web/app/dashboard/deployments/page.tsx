/** Deployments tab — staged deployment pipeline with stage track + canary metrics. */

"use client";

import { useState, useCallback } from "react";
import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import StageTrack from "@/components/deploy/stage-track";
import CanaryMetrics from "@/components/deploy/canary-metrics";
import StatusTag from "@/components/ui/status-tag";
import { T, FONT } from "@/styles/tokens";
import { useShipBridgeSocket, type SocketEvent } from "@/hooks/useShipBridgeSocket";

const MOCK_STAGES = [
  { name: "sandbox", label: "Sandbox", trafficPct: 0, status: "complete" as const },
  { name: "canary5", label: "Canary 5%", trafficPct: 5, status: "active" as const },
  { name: "canary25", label: "Canary 25%", trafficPct: 25, status: "pending" as const },
  { name: "production", label: "Production", trafficPct: 100, status: "pending" as const },
];

const MOCK_METRICS = [
  { label: "Success Rate", value: "93.2", delta: -2.8, unit: "%", invertDelta: false },
  { label: "P95 Latency", value: "285", delta: 35, unit: "ms", invertDelta: true },
  { label: "Cost/Task", value: "$0.021", delta: 0.003, unit: "", invertDelta: true },
  { label: "Escalation", value: "5.1", delta: 1.1, unit: "%", invertDelta: true },
];

const MOCK_HISTORY = [
  { id: "d1", project: "Support Agent", status: "complete", score: 82, stages: 4, duration: "18h 32m", date: "2026-03-28" },
  { id: "d2", project: "Review Bot", status: "rolled_back", score: 78, stages: 2, duration: "6h 15m", date: "2026-03-25" },
  { id: "d3", project: "Data Pipeline", status: "failed", score: 68, stages: 0, duration: "0m", date: "2026-03-22" },
];

const STATUS_MAP: Record<string, { status: "ok" | "warn" | "bad"; label: string }> = {
  complete: { status: "ok", label: "deployed" },
  rolled_back: { status: "warn", label: "rolled back" },
  failed: { status: "bad", label: "blocked" },
};

export default function DeploymentsPage() {
  const [stages, setStages] = useState(MOCK_STAGES);
  const [metrics, setMetrics] = useState(MOCK_METRICS);
  const [liveStatus, setLiveStatus] = useState<"in progress" | "complete" | "rolled back">("in progress");

  const { connected } = useShipBridgeSocket({
    tenantId: "demo-tenant",
    onEvent: useCallback((event: SocketEvent) => {
      if (event.type === "deployment_stage_update") {
        setStages((prev) =>
          prev.map((s) =>
            s.name === event.stage
              ? { ...s, status: event.status as typeof MOCK_STAGES[number]["status"] }
              : s
          ) as typeof MOCK_STAGES
        );
        if (event.status === "complete" && event.stage === "production") {
          setLiveStatus("complete");
        }
      }
    }, []),
  });

  return (
    <PageTransition pageKey="deployments">
      <Header
        title="Deployments"
        subtitle="Staged deployment pipeline"
        actions={
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: connected ? T.ok : T.t4 }} />
            <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              {connected ? "live" : "offline"}
            </span>
          </div>
        }
      />
      <div style={{ padding: "24px" }}>
        {/* Active deployment */}
        <div style={{
          backgroundColor: T.s1, borderRadius: "8px", border: `1px solid ${T.b0}`,
          padding: "20px 24px", marginBottom: "20px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <h3 style={{ fontFamily: FONT.ui, fontSize: 15, fontWeight: 600, color: T.t1, margin: 0 }}>
              Active Deployment
            </h3>
            <StatusTag status="ok" label="in progress" />
          </div>
          <StageTrack stages={stages} />
        </div>

        {/* Canary metrics */}
        <div style={{ marginBottom: "20px" }}>
          <CanaryMetrics metrics={metrics} health="healthy" />
        </div>

        {/* Manual controls */}
        <div style={{ display: "flex", gap: "8px", marginBottom: "24px" }}>
          <button type="button" style={{
            padding: "8px 16px", borderRadius: "6px", border: "none",
            backgroundColor: T.sig, color: T.s0, fontFamily: FONT.ui,
            fontSize: 13, fontWeight: 500, cursor: "pointer",
          }}>
            Advance to next stage
          </button>
          <button type="button" style={{
            padding: "8px 16px", borderRadius: "6px",
            border: `1px solid ${T.b2}`, backgroundColor: "transparent",
            color: T.danger, fontFamily: FONT.ui, fontSize: 13, cursor: "pointer",
          }}>
            Rollback
          </button>
        </div>

        {/* Deployment history */}
        <div style={{ backgroundColor: T.s1, borderRadius: "8px", border: `1px solid ${T.b0}`, overflow: "hidden" }}>
          <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.b0}` }}>
            <span style={{ fontFamily: FONT.ui, fontSize: 13, fontWeight: 500, color: T.t1 }}>Deployment History</span>
          </div>
          <div style={{
            display: "grid", gridTemplateColumns: "1fr 100px 60px 80px 100px 100px",
            padding: "8px 16px", borderBottom: `1px solid ${T.b0}`,
          }}>
            {["PROJECT", "STATUS", "SCORE", "STAGES", "DURATION", "DATE"].map((h) => (
              <span key={h} style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
            ))}
          </div>
          {MOCK_HISTORY.map((dep) => {
            const statusInfo = STATUS_MAP[dep.status] ?? { status: "neutral" as const, label: dep.status };
            return (
              <div key={dep.id} style={{
                display: "grid", gridTemplateColumns: "1fr 100px 60px 80px 100px 100px",
                padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
              }}>
                <span style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t1 }}>{dep.project}</span>
                <span><StatusTag status={statusInfo.status} label={statusInfo.label} /></span>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: dep.score >= 75 ? T.ok : T.warn }}>{dep.score}</span>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.t2 }}>{dep.stages}/4</span>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.t3 }}>{dep.duration}</span>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.t4 }}>{dep.date}</span>
              </div>
            );
          })}
        </div>
      </div>
    </PageTransition>
  );
}
