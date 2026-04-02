/** CanaryMetrics — 4-KPI grid comparing canary vs baseline with delta indicators. */

"use client";

import React, { useMemo } from "react";
import { T, FONT } from "@/styles/tokens";

interface MetricKPI {
  label: string;
  value: string;
  delta: number;
  unit: string;
  invertDelta?: boolean; // true = lower is better (e.g., latency)
}

interface CanaryMetricsProps {
  metrics: MetricKPI[];
  health: "healthy" | "regression" | "rollback_in_progress";
}

const HEALTH_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  healthy: { color: T.ok, bg: T.okDim, label: "HEALTHY" },
  regression: { color: T.danger, bg: T.dangerDim, label: "REGRESSION" },
  rollback_in_progress: { color: T.warn, bg: T.warnDim, label: "ROLLING BACK" },
};

const CanaryMetrics = React.memo(function CanaryMetrics({ metrics, health }: CanaryMetricsProps) {
  const healthStyle = HEALTH_STYLES[health] ?? HEALTH_STYLES.healthy;

  return (
    <div style={{ backgroundColor: T.s1, borderRadius: "8px", border: `1px solid ${T.b0}`, padding: "16px 20px" }}>
      {/* Health badge */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <span style={{ fontFamily: FONT.ui, fontSize: 13, fontWeight: 500, color: T.t1 }}>
          Canary Metrics
        </span>
        <span style={{
          fontFamily: FONT.label, fontSize: 10, fontWeight: 600, color: healthStyle.color,
          backgroundColor: healthStyle.bg, padding: "3px 8px", borderRadius: "4px",
          textTransform: "uppercase", letterSpacing: "0.04em",
        }}>
          {healthStyle.label}
        </span>
      </div>

      {/* KPI grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px" }}>
        {metrics.map((kpi) => {
          const isPositive = kpi.invertDelta ? kpi.delta < 0 : kpi.delta > 0;
          const isNeutral = kpi.delta === 0;
          const deltaColor = isNeutral ? T.t3 : isPositive ? T.ok : T.danger;
          const deltaPrefix = kpi.delta > 0 ? "+" : "";

          return (
            <div key={kpi.label}>
              <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>
                {kpi.label}
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                <span style={{ fontFamily: FONT.data, fontSize: 20, fontWeight: 500, color: T.t1 }}>
                  {kpi.value}
                </span>
                <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t3 }}>
                  {kpi.unit}
                </span>
              </div>
              <div style={{ fontFamily: FONT.data, fontSize: 11, color: deltaColor, marginTop: 2 }}>
                {deltaPrefix}{kpi.delta}{kpi.unit === "%" ? "pp" : kpi.unit === "ms" ? "ms" : ""}
                <span style={{ fontSize: 10, marginLeft: 2 }}>
                  {isPositive ? "▲" : kpi.delta < 0 ? "▼" : "—"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});

export default CanaryMetrics;
