/** HITL Gate — Human-in-the-loop rule approval and rejection interface. */

"use client";

import { useState, useEffect, useMemo } from "react";
import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import StatusTag from "@/components/ui/status-tag";
import { T, FONT } from "@/styles/tokens";
import { useApiGet, useApiPost } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";
import type { RuleListResponse, NormalizationRule } from "@/types/api";

interface DraftRule {
  id: string;
  trigger: string;
  provider: string;
  generated_at: string;
  status: "draft" | "active" | "archived";
  rule_logic: string;
  confidence: number;
  unknown_event_sample: string;
}

const mapRule = (r: NormalizationRule): DraftRule => ({
  id: r.rule_id,
  trigger: r.trigger,
  provider: r.app,
  generated_at: r.created_at,
  status: r.status as DraftRule["status"],
  rule_logic: JSON.stringify(r.payload_map, null, 2),
  confidence: 0.85, // Not available from API, use default
  unknown_event_sample: JSON.stringify(r.payload_map),
});

const FALLBACK_RULES: DraftRule[] = [
  {
    id: "r1",
    trigger: "trello.card_moved",
    provider: "trello",
    generated_at: "2026-04-01T12:30:00Z",
    status: "draft",
    rule_logic: 'if event.type == "card_moved" and event.list_name == "Done": trigger_assessment(project_id=event.board_id)',
    confidence: 0.87,
    unknown_event_sample: '{"type": "card_moved", "board_id": "abc123", "list_name": "Done", "card_id": "xyz789"}',
  },
  {
    id: "r2",
    trigger: "linear.issue_completed",
    provider: "linear",
    generated_at: "2026-04-01T11:15:00Z",
    status: "draft",
    rule_logic: 'if event.type == "issue_completed" and event.priority == "urgent": trigger_deployment(project_id=event.team_id)',
    confidence: 0.72,
    unknown_event_sample: '{"type": "issue_completed", "team_id": "team-01", "priority": "urgent", "issue_id": "LIN-42"}',
  },
  {
    id: "r3",
    trigger: "zendesk.ticket_resolved",
    provider: "zendesk",
    generated_at: "2026-03-31T09:00:00Z",
    status: "active",
    rule_logic: 'if event.type == "ticket_resolved" and event.satisfaction == "good": log_positive_signal(project_id=event.agent_id)',
    confidence: 0.95,
    unknown_event_sample: '{"type": "ticket_resolved", "agent_id": "agent-55", "satisfaction": "good", "ticket_id": "ZD-1001"}',
  },
];

export default function RulesPage() {
  const { data: ruleData, refetch } = useApiGet<RuleListResponse>(apiUrl("/api/v1/rules"));
  const { execute: promoteRule } = useApiPost<Record<string, unknown>, { app: string; trigger: string }>(apiUrl("/api/v1/rules/promote"));
  const { execute: archiveRule } = useApiPost<Record<string, unknown>, { app: string; trigger: string }>(apiUrl("/api/v1/rules/archive"));

  const apiRules = useMemo(() => {
    if (!ruleData?.rules) return null;
    return ruleData.rules.map(mapRule);
  }, [ruleData]);
  const [rules, setRules] = useState<DraftRule[]>(FALLBACK_RULES);

  useEffect(() => {
    if (apiRules) setRules(apiRules);
  }, [apiRules]);
  const [selected, setSelected] = useState<DraftRule | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const draftRules = rules.filter((r) => r.status === "draft");
  const activeRules = rules.filter((r) => r.status === "active");

  const handleApprove = async (rule: DraftRule) => {
    await promoteRule({ app: rule.provider, trigger: rule.trigger });
    refetch();
    setSelected(null);
    setActionMsg(`Rule "${rule.trigger}" approved and is now active.`);
    setTimeout(() => setActionMsg(null), 4000);
  };

  const handleReject = async (rule: DraftRule) => {
    await archiveRule({ app: rule.provider, trigger: rule.trigger });
    refetch();
    setSelected(null);
    setActionMsg(`Rule "${rule.trigger}" rejected and archived.`);
    setTimeout(() => setActionMsg(null), 4000);
  };

  const confidenceColor = (c: number) => c >= 0.85 ? T.ok : c >= 0.65 ? T.warn : T.danger;

  return (
    <PageTransition pageKey="rules">
      <Header title="HITL Gate" subtitle="Review and approve LLM-generated normalization rules" />
      <div style={{ padding: "24px" }}>

        {/* Action feedback banner */}
        {actionMsg && (
          <div style={{
            padding: "10px 16px", marginBottom: "16px", borderRadius: "6px",
            backgroundColor: "rgba(79,193,128,0.1)", border: `1px solid rgba(79,193,128,0.3)`,
            fontFamily: FONT.ui, fontSize: 13, color: T.ok,
          }}>
            {actionMsg}
          </div>
        )}

        {/* Stats strip */}
        <div style={{ display: "flex", gap: "16px", marginBottom: "24px" }}>
          {[
            { label: "PENDING REVIEW", value: draftRules.length.toString(), color: draftRules.length > 0 ? T.warn : T.ok },
            { label: "ACTIVE RULES", value: activeRules.length.toString(), color: T.ok },
            { label: "TOTAL RULES", value: rules.length.toString(), color: T.t2 },
          ].map((stat) => (
            <div key={stat.label} style={{
              flex: 1, padding: "16px", backgroundColor: T.s1,
              borderRadius: "8px", border: `1px solid ${T.b0}`,
            }}>
              <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                {stat.label}
              </div>
              <div style={{ fontFamily: FONT.data, fontSize: 22, fontWeight: 500, color: stat.color }}>
                {stat.value}
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: "grid", gridTemplateColumns: selected ? "1fr 420px" : "1fr", gap: "20px" }}>
          {/* Rules list */}
          <div style={{ backgroundColor: T.s1, borderRadius: "8px", border: `1px solid ${T.b0}`, overflow: "hidden" }}>
            <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.b0}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: FONT.ui, fontSize: 13, fontWeight: 500, color: T.t1 }}>Normalization Rules</span>
              <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3 }}>Click a draft to review</span>
            </div>
            <div style={{
              display: "grid", gridTemplateColumns: "1fr 100px 80px 90px 100px",
              padding: "8px 16px", borderBottom: `1px solid ${T.b0}`,
            }}>
              {["TRIGGER", "PROVIDER", "CONFIDENCE", "STATUS", "GENERATED"].map((h) => (
                <span key={h} style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.04em" }}>{h}</span>
              ))}
            </div>
            {rules.filter((r) => r.status !== "archived").map((rule) => (
              <div
                key={rule.id}
                onClick={() => rule.status === "draft" ? setSelected(rule) : null}
                style={{
                  display: "grid", gridTemplateColumns: "1fr 100px 80px 90px 100px",
                  padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
                  cursor: rule.status === "draft" ? "pointer" : "default",
                  backgroundColor: selected?.id === rule.id ? T.s2 : "transparent",
                  transition: "background-color 0.15s",
                }}
              >
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.t1 }}>{rule.trigger}</span>
                <span style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t2 }}>{rule.provider}</span>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: confidenceColor(rule.confidence) }}>
                  {(rule.confidence * 100).toFixed(0)}%
                </span>
                <span>
                  <StatusTag
                    status={rule.status === "active" ? "ok" : rule.status === "draft" ? "warn" : "neutral"}
                    label={rule.status}
                  />
                </span>
                <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t4 }}>
                  {new Date(rule.generated_at).toLocaleDateString()}
                </span>
              </div>
            ))}
          </div>

          {/* Rule detail / diff editor panel */}
          {selected && (
            <div style={{
              backgroundColor: T.s1, borderRadius: "8px", border: `1px solid ${T.b0}`,
              display: "flex", flexDirection: "column",
            }}>
              <div style={{ padding: "12px 16px", borderBottom: `1px solid ${T.b0}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontFamily: FONT.ui, fontSize: 13, fontWeight: 500, color: T.t1 }}>Review Draft Rule</span>
                <button
                  onClick={() => setSelected(null)}
                  style={{ background: "none", border: "none", color: T.t3, cursor: "pointer", fontSize: 16 }}
                >×</button>
              </div>

              <div style={{ padding: "16px", flex: 1, overflowY: "auto" }}>
                {/* Trigger info */}
                <div style={{ marginBottom: "16px" }}>
                  <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>TRIGGER</div>
                  <div style={{ fontFamily: FONT.data, fontSize: 13, color: T.sig }}>{selected.trigger}</div>
                </div>

                {/* Confidence */}
                <div style={{ marginBottom: "16px" }}>
                  <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>CONFIDENCE</div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <div style={{ flex: 1, height: 4, backgroundColor: T.s3, borderRadius: 2 }}>
                      <div style={{ width: `${selected.confidence * 100}%`, height: "100%", backgroundColor: confidenceColor(selected.confidence), borderRadius: 2 }} />
                    </div>
                    <span style={{ fontFamily: FONT.data, fontSize: 12, color: confidenceColor(selected.confidence) }}>
                      {(selected.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                {/* Sample event */}
                <div style={{ marginBottom: "16px" }}>
                  <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>SAMPLE EVENT</div>
                  <pre style={{
                    fontFamily: FONT.data, fontSize: 11, color: T.t2,
                    backgroundColor: T.s2, padding: "10px", borderRadius: "6px",
                    border: `1px solid ${T.b0}`, overflowX: "auto", margin: 0,
                    whiteSpace: "pre-wrap", wordBreak: "break-all",
                  }}>
                    {JSON.stringify(JSON.parse(selected.unknown_event_sample), null, 2)}
                  </pre>
                </div>

                {/* Generated rule logic */}
                <div style={{ marginBottom: "20px" }}>
                  <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>GENERATED RULE LOGIC</div>
                  <pre style={{
                    fontFamily: FONT.data, fontSize: 11, color: T.ok,
                    backgroundColor: "rgba(79,193,128,0.05)", padding: "10px", borderRadius: "6px",
                    border: `1px solid rgba(79,193,128,0.2)`, overflowX: "auto", margin: 0,
                    whiteSpace: "pre-wrap", wordBreak: "break-all",
                  }}>
                    {selected.rule_logic}
                  </pre>
                </div>

                {/* Action buttons */}
                <div style={{ display: "flex", gap: "8px" }}>
                  <button
                    onClick={() => handleApprove(selected)}
                    style={{
                      flex: 1, padding: "10px", borderRadius: "6px", border: "none",
                      backgroundColor: T.sig, color: T.s0, fontFamily: FONT.ui,
                      fontSize: 13, fontWeight: 500, cursor: "pointer",
                    }}
                  >
                    Approve & Activate
                  </button>
                  <button
                    onClick={() => handleReject(selected)}
                    style={{
                      flex: 1, padding: "10px", borderRadius: "6px",
                      border: `1px solid ${T.b2}`, backgroundColor: "transparent",
                      color: T.danger, fontFamily: FONT.ui, fontSize: 13, cursor: "pointer",
                    }}
                  >
                    Reject & Archive
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </PageTransition>
  );
}
