/** Cost breakdown chart with scale selector (1x / 10x / 100x). */

"use client";

import React, { useCallback, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { T, FONT } from "@/styles/tokens";

interface CostProjection {
  scale_label: string;
  monthly_tasks: number;
  models_used: string[];
  cost_per_model: Record<string, number>;
  total_monthly_cost: number;
  cost_per_task: number;
  cache_savings: number;
  effective_cost: number;
}

interface CostChartProps {
  projections: CostProjection[];
  routingRecommendation: string;
}

const MODEL_COLORS: Record<string, string> = {
  "claude-3-haiku": "#2A9D6E",
  "claude-3-5-haiku": "#2A9D6E",
  "claude-3-5-sonnet": T.sig,
  "claude-sonnet-4": T.sig,
  "claude-opus-4": "#9B59B6",
  "gpt-4o": "#3498DB",
  "gpt-4o-mini": "#1ABC9C",
};

// Module-level variants
const BAR_VARIANTS = {
  initial: { scaleX: 0 },
  animate: { scaleX: 1 },
};

const CostChart = React.memo(function CostChart({ projections, routingRecommendation }: CostChartProps) {
  const [selectedScale, setSelectedScale] = useState(0);

  const handleScaleChange = useCallback((idx: number) => {
    setSelectedScale(idx);
  }, []);

  const current = projections[selectedScale];
  const maxCost = useMemo(
    () => Math.max(...projections.map((p) => p.total_monthly_cost), 1),
    [projections],
  );

  if (!current) return null;

  return (
    <div
      style={{
        backgroundColor: T.s1,
        borderRadius: "8px",
        border: `1px solid ${T.b0}`,
        padding: "20px",
      }}
    >
      {/* Scale selector */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <h3 style={{ fontFamily: FONT.ui, fontSize: 15, fontWeight: 600, color: T.t1, margin: 0 }}>
          Cost Projection
        </h3>
        <div style={{ display: "flex", gap: 4 }}>
          {projections.map((p, idx) => (
            <button
              key={p.scale_label}
              onClick={() => handleScaleChange(idx)}
              type="button"
              style={{
                padding: "4px 12px",
                borderRadius: "4px",
                border: "none",
                fontSize: 12,
                fontFamily: FONT.data,
                fontWeight: 500,
                cursor: "pointer",
                color: selectedScale === idx ? T.s0 : T.t2,
                backgroundColor: selectedScale === idx ? T.sig : T.s3,
                transition: "all 0.15s ease",
              }}
            >
              {p.scale_label}
            </button>
          ))}
        </div>
      </div>

      {/* Summary stats */}
      <div style={{ display: "flex", gap: 24, marginBottom: 20 }}>
        <div>
          <span style={{ fontFamily: FONT.data, fontSize: 24, fontWeight: 500, color: T.t1 }}>
            ${current.effective_cost.toLocaleString()}
          </span>
          <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
            /month
          </span>
        </div>
        <div>
          <span style={{ fontFamily: FONT.data, fontSize: 16, color: T.t2 }}>
            ${current.cost_per_task.toFixed(4)}
          </span>
          <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
            /task
          </span>
        </div>
        <div>
          <span style={{ fontFamily: FONT.data, fontSize: 16, color: T.t2 }}>
            {current.monthly_tasks.toLocaleString()}
          </span>
          <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
            tasks
          </span>
        </div>
        {current.cache_savings > 0 && (
          <div>
            <span style={{ fontFamily: FONT.data, fontSize: 16, color: T.ok }}>
              -${current.cache_savings.toLocaleString()}
            </span>
            <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, marginLeft: 4, textTransform: "uppercase" }}>
              cache savings
            </span>
          </div>
        )}
      </div>

      {/* Per-model cost bars */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 16 }}>
        {Object.entries(current.cost_per_model).map(([model, cost]) => {
          const pct = (cost / current.total_monthly_cost) * 100;
          const color = MODEL_COLORS[model] ?? T.t3;
          return (
            <div key={model} style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t2, minWidth: 140, textAlign: "right" }}>
                {model}
              </span>
              <div style={{ flex: 1, height: 12, backgroundColor: T.s3, borderRadius: 2, overflow: "hidden" }}>
                <motion.div
                  variants={BAR_VARIANTS}
                  initial="initial"
                  animate="animate"
                  transition={{ duration: 0.5, ease: "easeOut" }}
                  style={{
                    width: `${pct}%`,
                    height: "100%",
                    backgroundColor: color,
                    borderRadius: 2,
                    transformOrigin: "left",
                  }}
                />
              </div>
              <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t1, minWidth: 60 }}>
                ${cost.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>

      {/* Routing recommendation */}
      <p style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t3, margin: 0 }}>
        {routingRecommendation}
      </p>
    </div>
  );
});

export default CostChart;
