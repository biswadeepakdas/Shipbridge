/** Governance tab — HITL approval queue and audit log. */

"use client";

import { useState, useCallback } from "react";
import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import StatusTag from "@/components/ui/status-tag";
import { T, FONT } from "@/styles/tokens";
import { useApiGet } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";

type Tab = "hitl" | "audit";

interface HITLGate {
  id: string;
  title: string;
  description: string;
  requested_by: string;
  resource_type: string;
  risk_level: string;
  status: "pending" | "approved" | "rejected" | "expired";
  details: Record<string, unknown>;
  requested_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
}

interface AuditEntry {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  user_id: string | null;
  agent_id: string | null;
  created_at: string;
}

const RISK_STATUS: Record<string, "ok" | "warn" | "bad"> = {
  low: "ok",
  medium: "warn",
  high: "bad",
  critical: "bad",
};

const GATE_STATUS: Record<string, { status: "ok" | "warn" | "bad" | "neutral"; label: string }> = {
  pending: { status: "warn", label: "pending" },
  approved: { status: "ok", label: "approved" },
  rejected: { status: "bad", label: "rejected" },
  expired: { status: "neutral", label: "expired" },
};

export default function GovernancePage() {
  const [tab, setTab] = useState<Tab>("hitl");

  const { data: gates, refetch: refreshGates } = useApiGet<HITLGate[]>(
    apiUrl("/api/v1/governance/gates")
  );
  const { data: auditEntries } = useApiGet<AuditEntry[]>(
    apiUrl("/api/v1/governance/audit")
  );

  const handleApprove = useCallback(async (gateId: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    await fetch(apiUrl(`/api/v1/governance/gates/${gateId}/approve`), {
      method: "POST", headers, body: JSON.stringify({}),
    });
    refreshGates();
  }, [refreshGates]);

  const handleReject = useCallback(async (gateId: string) => {
    const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
    const headers: HeadersInit = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    await fetch(apiUrl(`/api/v1/governance/gates/${gateId}/reject`), {
      method: "POST", headers, body: JSON.stringify({}),
    });
    refreshGates();
  }, [refreshGates]);

  const pendingCount = gates?.filter((g) => g.status === "pending").length ?? 0;

  return (
    <PageTransition pageKey="governance">
      <Header title="Governance" subtitle="HITL approvals and audit trail" />
      <div style={{ padding: "24px" }}>
        {/* Tab switcher */}
        <div style={{ display: "flex", gap: "4px", marginBottom: "20px", backgroundColor: T.s2, borderRadius: "6px", padding: "3px", width: "fit-content" }}>
          {(["hitl", "audit"] as Tab[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              style={{
                padding: "6px 16px", borderRadius: "4px", border: "none",
                backgroundColor: tab === t ? T.s1 : "transparent",
                color: tab === t ? T.t1 : T.t3, fontFamily: FONT.ui,
                fontSize: 12, fontWeight: 500, cursor: "pointer",
              }}
            >
              {t === "hitl" ? `HITL Queue${pendingCount > 0 ? ` (${pendingCount})` : ""}` : "Audit Log"}
            </button>
          ))}
        </div>

        {tab === "hitl" && (
          <div>
            {pendingCount > 0 && (
              <div style={{
                padding: "12px 16px", marginBottom: "16px", backgroundColor: T.warnDim,
                borderRadius: "6px", border: "1px solid rgba(196,154,60,0.2)",
              }}>
                <span style={{ fontFamily: FONT.ui, fontSize: 13, color: T.warn }}>
                  {pendingCount} approval(s) waiting for review
                </span>
              </div>
            )}

            <div style={{ backgroundColor: T.s1, borderRadius: "8px", border: `1px solid ${T.b0}`, overflow: "hidden" }}>
              <div style={{
                display: "grid", gridTemplateColumns: "1fr 120px 80px 100px 150px",
                padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
              }}>
                {["TITLE", "RESOURCE", "RISK", "STATUS", "ACTIONS"].map((h) => (
                  <span key={h} style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
                ))}
              </div>
              {(gates ?? []).map((gate) => {
                const statusInfo = GATE_STATUS[gate.status] ?? { status: "neutral" as const, label: gate.status };
                return (
                  <div key={gate.id} style={{
                    display: "grid", gridTemplateColumns: "1fr 120px 80px 100px 150px",
                    padding: "12px 16px", borderBottom: `1px solid ${T.b0}`, alignItems: "center",
                  }}>
                    <div>
                      <div style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t1 }}>{gate.title}</div>
                      <div style={{ fontFamily: FONT.ui, fontSize: 11, color: T.t3, marginTop: 2 }}>{gate.description}</div>
                    </div>
                    <span style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t2 }}>{gate.resource_type}</span>
                    <StatusTag status={RISK_STATUS[gate.risk_level] ?? "warn"} label={gate.risk_level} />
                    <StatusTag status={statusInfo.status} label={statusInfo.label} />
                    <div style={{ display: "flex", gap: "6px" }}>
                      {gate.status === "pending" && (
                        <>
                          <button type="button" onClick={() => handleApprove(gate.id)} style={{
                            padding: "4px 10px", borderRadius: "4px", border: "none",
                            backgroundColor: T.ok, color: T.s0, fontFamily: FONT.ui, fontSize: 11, cursor: "pointer",
                          }}>Approve</button>
                          <button type="button" onClick={() => handleReject(gate.id)} style={{
                            padding: "4px 10px", borderRadius: "4px", border: `1px solid ${T.danger}`,
                            backgroundColor: "transparent", color: T.danger, fontFamily: FONT.ui, fontSize: 11, cursor: "pointer",
                          }}>Reject</button>
                        </>
                      )}
                    </div>
                  </div>
                );
              })}
              {(!gates || gates.length === 0) && (
                <div style={{ padding: "24px", textAlign: "center", fontFamily: FONT.ui, fontSize: 13, color: T.t3 }}>
                  No HITL gates found. Gates are created when high-risk actions require approval.
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "audit" && (
          <div style={{ backgroundColor: T.s1, borderRadius: "8px", border: `1px solid ${T.b0}`, overflow: "hidden" }}>
            <div style={{
              display: "grid", gridTemplateColumns: "120px 120px 120px 1fr 140px",
              padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
            }}>
              {["ACTION", "RESOURCE", "RESOURCE ID", "DETAILS", "TIMESTAMP"].map((h) => (
                <span key={h} style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
              ))}
            </div>
            {(auditEntries ?? []).map((entry) => (
              <div key={entry.id} style={{
                display: "grid", gridTemplateColumns: "120px 120px 120px 1fr 140px",
                padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
              }}>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.sig }}>{entry.action}</span>
                <span style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t2 }}>{entry.resource_type}</span>
                <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t3 }}>{entry.resource_id ?? "—"}</span>
                <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t3, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {JSON.stringify(entry.details).slice(0, 80)}
                </span>
                <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t4 }}>
                  {new Date(entry.created_at).toLocaleString()}
                </span>
              </div>
            ))}
            {(!auditEntries || auditEntries.length === 0) && (
              <div style={{ padding: "24px", textAlign: "center", fontFamily: FONT.ui, fontSize: 13, color: T.t3 }}>
                No audit entries yet. Actions will be logged as the platform is used.
              </div>
            )}
          </div>
        )}
      </div>
    </PageTransition>
  );
}
