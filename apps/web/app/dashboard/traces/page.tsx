/** Traces tab — runtime trace viewer with filters and summary stats. */

"use client";

import { useCallback, useMemo, useState } from "react";
import { T, FONT } from "@/styles/tokens";
import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import StatusTag from "@/components/ui/status-tag";
import { useApiGet } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";
import type { ProjectOut, RuntimeTraceOut } from "@/types/api";

export default function TracesPage() {
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [operationFilter, setOperationFilter] = useState<string>("");

  // Fetch first project
  const { data: projects } = useApiGet<ProjectOut[]>(apiUrl("/api/v1/projects"));
  const projectId = projects?.[0]?.id;

  // Build query params
  const queryParams = useMemo(() => {
    const params = new URLSearchParams();
    params.set("limit", "100");
    if (statusFilter !== "all") params.set("status", statusFilter);
    if (operationFilter) params.set("operation", operationFilter);
    return params.toString();
  }, [statusFilter, operationFilter]);

  // Fetch traces
  const { data: traces, isLoading } = useApiGet<RuntimeTraceOut[]>(
    projectId ? apiUrl(`/api/v1/projects/${projectId}/traces?${queryParams}`) : null,
  );

  // Summary stats
  const stats = useMemo(() => {
    if (!traces || traces.length === 0) {
      return { total: 0, avgDuration: 0, errorRate: 0, topOps: [] as string[] };
    }
    const total = traces.length;
    const errors = traces.filter((t) => t.status === "error").length;
    const avgDuration = traces.reduce((sum, t) => sum + t.duration_ms, 0) / total;

    // Top operations by frequency
    const opCounts: Record<string, number> = {};
    for (const t of traces) {
      opCounts[t.operation] = (opCounts[t.operation] ?? 0) + 1;
    }
    const topOps = Object.entries(opCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([op]) => op);

    return {
      total,
      avgDuration: Math.round(avgDuration),
      errorRate: total > 0 ? errors / total : 0,
      topOps,
    };
  }, [traces]);

  const filterBtnStyle = (active: boolean) => ({
    padding: "6px 12px",
    borderRadius: 4,
    border: `1px solid ${active ? T.sig : T.b1}`,
    backgroundColor: active ? T.sigDim : "transparent",
    color: active ? T.sig : T.t3,
    fontFamily: FONT.ui,
    fontSize: 11,
    cursor: "pointer" as const,
  });

  return (
    <PageTransition pageKey="traces">
      <Header title="Traces" subtitle="Runtime trace viewer" />
      <div style={{ padding: "24px" }}>
        {/* Summary stats */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          marginBottom: 20,
        }}>
          {[
            { label: "TOTAL TRACES", value: stats.total, color: T.t1 },
            { label: "AVG DURATION", value: `${stats.avgDuration}ms`, color: T.sig },
            { label: "ERROR RATE", value: `${(stats.errorRate * 100).toFixed(1)}%`, color: stats.errorRate > 0.05 ? T.danger : T.ok },
            { label: "TOP OPERATION", value: stats.topOps[0] ?? "—", color: T.t2 },
          ].map((stat) => (
            <div
              key={stat.label}
              style={{
                padding: "14px 16px",
                backgroundColor: T.s1,
                borderRadius: 8,
                border: `1px solid ${T.b0}`,
              }}
            >
              <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", marginBottom: 4 }}>
                {stat.label}
              </div>
              <div style={{ fontFamily: FONT.data, fontSize: 18, fontWeight: 500, color: stat.color }}>
                {stat.value}
              </div>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div style={{ display: "flex", gap: 8, marginBottom: 16, alignItems: "center" }}>
          <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", marginRight: 4 }}>
            STATUS:
          </span>
          {["all", "ok", "error"].map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setStatusFilter(s)}
              style={filterBtnStyle(statusFilter === s)}
            >
              {s.toUpperCase()}
            </button>
          ))}
          <div style={{ marginLeft: 16, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase" }}>
              OPERATION:
            </span>
            <input
              value={operationFilter}
              onChange={(e) => setOperationFilter(e.target.value)}
              placeholder="filter..."
              style={{
                padding: "4px 10px",
                borderRadius: 4,
                border: `1px solid ${T.b1}`,
                backgroundColor: T.s2,
                color: T.t1,
                fontFamily: FONT.data,
                fontSize: 11,
                outline: "none",
                width: 140,
              }}
            />
          </div>
        </div>

        {/* Traces table */}
        <div style={{
          backgroundColor: T.s1,
          borderRadius: 8,
          border: `1px solid ${T.b0}`,
          overflow: "hidden",
        }}>
          {/* Header */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "160px 1fr 80px 90px 100px 100px 140px",
            padding: "10px 16px",
            backgroundColor: T.s2,
            borderBottom: `1px solid ${T.b0}`,
          }}>
            {["TIME", "OPERATION", "STATUS", "DURATION", "MODEL", "TOOL", "TRACE ID"].map((h) => (
              <span key={h} style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase" }}>
                {h}
              </span>
            ))}
          </div>

          {isLoading && (
            <div style={{ padding: 40, textAlign: "center", color: T.t3, fontFamily: FONT.ui, fontSize: 13 }}>
              Loading traces...
            </div>
          )}

          {!isLoading && (!traces || traces.length === 0) && (
            <div style={{ padding: 40, textAlign: "center", color: T.t3, fontFamily: FONT.ui, fontSize: 13 }}>
              No traces found. Instrument your agent with the ShipBridge SDK to see runtime data.
            </div>
          )}

          {(traces ?? []).map((trace) => (
            <div
              key={trace.id}
              style={{
                display: "grid",
                gridTemplateColumns: "160px 1fr 80px 90px 100px 100px 140px",
                padding: "10px 16px",
                borderBottom: `1px solid ${T.b0}`,
                alignItems: "center",
              }}
            >
              <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t2 }}>
                {new Date(trace.started_at).toLocaleString()}
              </span>
              <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t1 }}>
                {trace.operation}
              </span>
              <StatusTag
                status={trace.status === "ok" ? "ok" : "bad"}
                label={trace.status}
              />
              <span style={{ fontFamily: FONT.data, fontSize: 11, color: trace.duration_ms > 3000 ? T.warn : T.t2 }}>
                {trace.duration_ms.toFixed(0)}ms
              </span>
              <span style={{ fontFamily: FONT.data, fontSize: 10, color: T.t3 }}>
                {trace.model ?? "—"}
              </span>
              <span style={{ fontFamily: FONT.data, fontSize: 10, color: T.t3 }}>
                {trace.tool_name ?? "—"}
              </span>
              <span style={{ fontFamily: FONT.data, fontSize: 10, color: T.t4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {trace.trace_id.slice(0, 12)}...
              </span>
            </div>
          ))}
        </div>
      </div>
    </PageTransition>
  );
}
