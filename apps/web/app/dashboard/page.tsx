/** Overview tab — pillar cards, score arc, readiness summary, ingestion sources, trace summary, and issue drill-down. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { T, FONT } from "@/styles/tokens";
import Header from "@/components/dashboard/header";
import PillarCard from "@/components/dashboard/pillar-card";
import ScoreArc from "@/components/ui/score-arc";
import IssueList from "@/components/dashboard/issue-list";
import StatusTag from "@/components/ui/status-tag";
import PageTransition from "@/components/dashboard/page-transition";
import { useApiGet, useApiPost } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";
import type { ProjectOut, AssessmentRunOut, Issue, IngestionSourceOut, RuntimeTraceOut } from "@/types/api";

interface PillarData {
  id: string;
  label: string;
  score: number;
  status: "ok" | "warn" | "bad";
  note: string;
  issues: Issue[];
}

// Fallback data used when no API data is available
const FALLBACK_PILLARS: PillarData[] = [
  {
    id: "reliability", label: "Reliability", score: 80, status: "ok",
    note: "Compound accuracy above threshold",
    issues: [
      { title: "Single model dependency", evidence: "Only claude-3-5-sonnet configured as primary", fix_hint: "Add a fallback model for resilience", severity: "medium", effort_days: 1 },
    ],
  },
  {
    id: "security", label: "Security", score: 60, status: "warn",
    note: "MCP endpoints need auth review",
    issues: [
      { title: "No prompt injection guard", evidence: "Agent accepts user input without injection filtering", fix_hint: "Add input sanitization and prompt injection detection", severity: "high", effort_days: 2 },
      { title: "No authentication configured", evidence: "Missing auth field in stack config", fix_hint: "Add OAuth2 or API key authentication to all endpoints", severity: "high", effort_days: 2 },
    ],
  },
  {
    id: "eval", label: "Eval", score: 75, status: "ok",
    note: "CI grader present, baseline captured",
    issues: [
      { title: "Low test coverage", evidence: "Test coverage at 65%", fix_hint: "Increase test coverage to 80%+ for production readiness", severity: "medium", effort_days: 3 },
    ],
  },
  {
    id: "governance", label: "Governance", score: 70, status: "warn",
    note: "HITL gates not configured",
    issues: [
      { title: "No human-in-the-loop gates", evidence: "No HITL approval required for high-risk actions", fix_hint: "Configure HITL gates for actions above risk threshold", severity: "high", effort_days: 3 },
      { title: "No audit trail configured", evidence: "Agent actions are not logged to immutable audit log", fix_hint: "Enable audit logging for all tool calls and LLM decisions", severity: "high", effort_days: 2 },
    ],
  },
  {
    id: "cost", label: "Cost", score: 75, status: "ok",
    note: "Model routing optimized for 3 tiers",
    issues: [
      { title: "No semantic cache", evidence: "Repeated queries hit the model every time", fix_hint: "Add semantic cache with Redis to reduce redundant LLM calls", severity: "medium", effort_days: 2 },
    ],
  },
];

// Module-level animation variants
const DRILLDOWN_VARIANTS = {
  hidden: { opacity: 0, height: 0 },
  visible: { opacity: 1, height: "auto" },
};

const MODE_LABELS: Record<string, string> = {
  github_repo: "GitHub Repo",
  runtime_endpoint: "Runtime Endpoint",
  sdk_instrumentation: "SDK",
  manifest: "Manifest",
};

const STATUS_MAP: Record<string, "ok" | "warn" | "bad" | "neutral"> = {
  active: "ok",
  pending: "neutral",
  validating: "warn",
  failed: "bad",
};

export default function OverviewPage() {
  const [activePillar, setActivePillar] = useState<string | null>(null);
  const [isRunningAssessment, setIsRunningAssessment] = useState(false);

  // Fetch projects — use first project for demo
  const { data: projects } = useApiGet<ProjectOut[]>(apiUrl("/api/v1/projects"));
  const projectId = projects?.[0]?.id;

  // Fetch latest assessment for the project
  const { data: assessments, isLoading, refetch: refetchAssessments } = useApiGet<AssessmentRunOut[]>(
    projectId ? apiUrl(`/api/v1/projects/${projectId}/assessments`) : null
  );

  // Fetch ingestion sources
  const { data: ingestionSources } = useApiGet<IngestionSourceOut[]>(
    projectId ? apiUrl(`/api/v1/projects/${projectId}/ingestion`) : null
  );

  // Fetch traces (just for summary)
  const { data: traces } = useApiGet<RuntimeTraceOut[]>(
    projectId ? apiUrl(`/api/v1/projects/${projectId}/traces?limit=50`) : null
  );

  // Convert API assessment data to pillar display format
  const pillars = useMemo(() => {
    if (!assessments || assessments.length === 0) return FALLBACK_PILLARS;
    const latest = assessments[0];
    const pillarOrder = ["reliability", "security", "eval", "governance", "cost"];
    return pillarOrder.map((id) => {
      const p = latest.scores_json[id];
      if (!p) return FALLBACK_PILLARS.find((f) => f.id === id)!;
      return {
        id,
        label: id.charAt(0).toUpperCase() + id.slice(1),
        score: p.score,
        status: p.status as "ok" | "warn" | "bad",
        note: p.note,
        issues: p.issues,
      };
    });
  }, [assessments]);

  const handlePillarClick = useCallback((id: string) => {
    setActivePillar((prev) => (prev === id ? null : id));
  }, []);

  const totalScore = useMemo(
    () => Math.round(pillars.reduce((sum, p) => sum + p.score, 0) / pillars.length),
    [pillars],
  );

  const activePillarData = useMemo(
    () => pillars.find((p) => p.id === activePillar),
    [activePillar, pillars],
  );

  const gapSummary = useMemo(() => {
    const allIssues = pillars.flatMap((p) => p.issues);
    return {
      total: allIssues.length,
      critical: allIssues.filter((i) => i.severity === "high").length,
      totalDays: allIssues.reduce((sum, i) => sum + i.effort_days, 0),
    };
  }, [pillars]);

  // Trace summary
  const traceSummary = useMemo(() => {
    if (!traces || traces.length === 0) return null;
    const total = traces.length;
    const errors = traces.filter((t) => t.status === "error").length;
    const avgDuration = traces.reduce((sum, t) => sum + t.duration_ms, 0) / total;
    return {
      total,
      errorRate: errors / total,
      avgDuration: Math.round(avgDuration),
    };
  }, [traces]);

  const handleRunAssessment = useCallback(async () => {
    if (!projectId || isRunningAssessment) return;
    setIsRunningAssessment(true);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
      const headers: HeadersInit = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;

      await fetch(apiUrl(`/api/v1/projects/${projectId}/assess`), {
        method: "POST",
        headers,
      });
      refetchAssessments();
    } catch {
      // silently handle
    } finally {
      setIsRunningAssessment(false);
    }
  }, [projectId, isRunningAssessment, refetchAssessments]);

  const handleDownloadPDF = useCallback(async () => {
    if (!projectId) return;
    const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
    const headers: HeadersInit = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const response = await fetch(apiUrl(`/api/v1/governance/pdf/${projectId}/download`), { headers });
    if (response.ok) {
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `shipbridge-compliance-${projectId}.pdf`;
      a.click();
      window.URL.revokeObjectURL(url);
    }
  }, [projectId]);

  return (
    <PageTransition pageKey="overview">
      <Header
        title="Overview"
        subtitle="Production readiness assessment"
        actions={
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              onClick={handleRunAssessment}
              disabled={isRunningAssessment}
              style={{
                padding: "8px 14px", borderRadius: "6px",
                border: "none", backgroundColor: T.sig,
                color: T.s0, fontFamily: FONT.ui, fontSize: 12,
                fontWeight: 500, cursor: isRunningAssessment ? "not-allowed" : "pointer",
                opacity: isRunningAssessment ? 0.6 : 1,
              }}
            >
              {isRunningAssessment ? "Running..." : "Run Assessment"}
            </button>
            <button
              type="button"
              onClick={handleDownloadPDF}
              style={{
                padding: "8px 14px", borderRadius: "6px",
                border: `1px solid ${T.b2}`, backgroundColor: "transparent",
                color: T.t2, fontFamily: FONT.ui, fontSize: 12,
                cursor: "pointer", display: "flex", alignItems: "center", gap: "6px",
              }}
            >
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
                <path d="M6.5 1v8M3.5 6.5l3 3 3-3" />
                <path d="M1 10.5v1a.5.5 0 00.5.5h10a.5.5 0 00.5-.5v-1" />
              </svg>
              Compliance PDF
            </button>
          </div>
        }
      />
      <div style={{ padding: "24px" }}>
        {isLoading && (
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", padding: "48px", fontFamily: FONT.ui, fontSize: 14, color: T.t2 }}>
            Loading assessment data...
          </div>
        )}
        {/* Score + summary row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "32px",
            marginBottom: "24px",
            padding: "24px",
            backgroundColor: T.s1,
            borderRadius: "8px",
            border: `1px solid ${T.b0}`,
          }}
        >
          <ScoreArc score={totalScore} size={140} />
          <div style={{ flex: 1 }}>
            <h2 style={{ fontFamily: FONT.ui, fontSize: 18, fontWeight: 600, color: T.t1, margin: 0 }}>
              {totalScore >= 75 ? "Ready for production" : "Not yet ready"}
            </h2>
            <p style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t2, marginTop: 4 }}>
              {totalScore >= 75
                ? "All pillars meet the minimum threshold. Proceed with staged deployment."
                : `Score ${totalScore}/100 \u2014 address blockers in the gap report to reach 75.`}
            </p>
            {/* Gap summary stats */}
            <div style={{ display: "flex", gap: "20px", marginTop: 12 }}>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 16, fontWeight: 500, color: gapSummary.critical > 0 ? T.danger : T.ok }}>
                  {gapSummary.critical}
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
                  critical
                </span>
              </div>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 16, fontWeight: 500, color: T.t1 }}>
                  {gapSummary.total}
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
                  total issues
                </span>
              </div>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 16, fontWeight: 500, color: T.t2 }}>
                  {gapSummary.totalDays}d
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
                  est. effort
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Pillar cards grid */}
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginBottom: "16px" }}>
          {pillars.map((pillar) => (
            <PillarCard
              key={pillar.id}
              pillar={pillar}
              isActive={activePillar === pillar.id}
              onClick={handlePillarClick}
            />
          ))}
        </div>

        {/* Drill-down panel */}
        <AnimatePresence>
          {activePillarData && (
            <motion.div
              key={activePillarData.id}
              variants={DRILLDOWN_VARIANTS}
              initial="hidden"
              animate="visible"
              exit="hidden"
              transition={{ duration: 0.25 }}
              style={{
                overflow: "hidden",
                backgroundColor: T.s1,
                borderRadius: "8px",
                border: `1px solid ${T.b1}`,
                padding: "16px 20px",
                marginBottom: "16px",
              }}
            >
              <IssueList
                issues={activePillarData.issues}
                pillarLabel={activePillarData.label}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Ingestion Sources Section */}
        {ingestionSources && ingestionSources.length > 0 && (
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ fontFamily: FONT.ui, fontSize: 14, fontWeight: 500, color: T.t1, marginBottom: 12 }}>
              Ingestion Sources
            </h3>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {ingestionSources.map((src) => (
                <div
                  key={src.id}
                  style={{
                    padding: "12px 16px",
                    backgroundColor: T.s1,
                    borderRadius: 8,
                    border: `1px solid ${T.b0}`,
                    minWidth: 180,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                    <span style={{ fontFamily: FONT.ui, fontSize: 12, fontWeight: 500, color: T.t1 }}>
                      {MODE_LABELS[src.mode] ?? src.mode}
                    </span>
                    <StatusTag status={STATUS_MAP[src.status] ?? "neutral"} label={src.status} />
                  </div>
                  <div style={{ fontFamily: FONT.data, fontSize: 10, color: T.t3 }}>
                    {src.last_synced_at ? `Synced ${new Date(src.last_synced_at).toLocaleDateString()}` : "Not synced"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Trace Summary Section */}
        {traceSummary && (
          <div style={{
            padding: "16px 20px",
            backgroundColor: T.s1,
            borderRadius: 8,
            border: `1px solid ${T.b0}`,
          }}>
            <h3 style={{ fontFamily: FONT.ui, fontSize: 14, fontWeight: 500, color: T.t1, marginBottom: 12 }}>
              Runtime Traces
            </h3>
            <div style={{ display: "flex", gap: 24 }}>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 18, fontWeight: 500, color: T.sig }}>
                  {traceSummary.total}
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 6, textTransform: "uppercase" }}>
                  traces
                </span>
              </div>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 18, fontWeight: 500, color: T.t1 }}>
                  {traceSummary.avgDuration}ms
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 6, textTransform: "uppercase" }}>
                  avg duration
                </span>
              </div>
              <div>
                <span style={{ fontFamily: FONT.data, fontSize: 18, fontWeight: 500, color: traceSummary.errorRate > 0.05 ? T.danger : T.ok }}>
                  {(traceSummary.errorRate * 100).toFixed(1)}%
                </span>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 6, textTransform: "uppercase" }}>
                  error rate
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </PageTransition>
  );
}
