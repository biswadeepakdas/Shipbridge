/** Costs tab — cost projection with 1x/10x/100x scale selector and model breakdown. */

"use client";

import { useState, useCallback, useMemo } from "react";
import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import CostChart from "@/components/dashboard/cost-chart";
import { T, FONT } from "@/styles/tokens";
import { useApiGet, useApiPost } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";
import type { ProjectOut } from "@/types/api";

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

interface CostModelOutput {
  projections: CostProjection[];
  routing_recommendation: string;
}

const FALLBACK_PROJECTIONS: CostProjection[] = [
  {
    scale_label: "1x",
    monthly_tasks: 1000,
    models_used: ["claude-3-5-haiku", "claude-3-5-sonnet"],
    cost_per_model: { "claude-3-5-haiku": 2.5, "claude-3-5-sonnet": 15.0 },
    total_monthly_cost: 17.5,
    cost_per_task: 0.0175,
    cache_savings: 3.5,
    effective_cost: 14.0,
  },
  {
    scale_label: "10x",
    monthly_tasks: 10000,
    models_used: ["claude-3-5-haiku", "claude-3-5-sonnet"],
    cost_per_model: { "claude-3-5-haiku": 25.0, "claude-3-5-sonnet": 150.0 },
    total_monthly_cost: 175.0,
    cost_per_task: 0.0175,
    cache_savings: 52.5,
    effective_cost: 122.5,
  },
  {
    scale_label: "100x",
    monthly_tasks: 100000,
    models_used: ["claude-3-5-haiku", "claude-3-5-sonnet"],
    cost_per_model: { "claude-3-5-haiku": 250.0, "claude-3-5-sonnet": 1500.0 },
    total_monthly_cost: 1750.0,
    cost_per_task: 0.0175,
    cache_savings: 700.0,
    effective_cost: 1050.0,
  },
];

export default function CostsPage() {
  const { data: projects } = useApiGet<ProjectOut[]>(apiUrl("/api/v1/projects"));
  const projectId = projects?.[0]?.id;

  const { execute: fetchProjection, data: costData, isLoading } = useApiPost<CostModelOutput, Record<string, unknown>>(
    projectId ? apiUrl(`/api/v1/projects/${projectId}/cost-projection`) : apiUrl("/api/v1/projects/_/cost-projection")
  );

  const [hasFetched, setHasFetched] = useState(false);

  const handleGenerate = useCallback(async () => {
    if (!projectId) return;
    await fetchProjection({});
    setHasFetched(true);
  }, [projectId, fetchProjection]);

  const projections = costData?.projections ?? (hasFetched ? [] : FALLBACK_PROJECTIONS);
  const recommendation = costData?.routing_recommendation ?? "Configure models in your project stack to see routing recommendations.";

  return (
    <PageTransition pageKey="costs">
      <Header
        title="Costs"
        subtitle="Token usage projections and model routing optimization"
        actions={
          <button
            type="button"
            onClick={handleGenerate}
            disabled={isLoading || !projectId}
            style={{
              padding: "8px 16px",
              borderRadius: "6px",
              border: "none",
              backgroundColor: !projectId ? T.s3 : T.sig,
              color: !projectId ? T.t3 : T.s0,
              fontFamily: FONT.ui,
              fontSize: 13,
              fontWeight: 500,
              cursor: !projectId ? "default" : "pointer",
              opacity: isLoading ? 0.6 : 1,
            }}
          >
            {isLoading ? "Calculating..." : "Generate Projection"}
          </button>
        }
      />
      <div style={{ padding: "24px" }}>
        {projections.length > 0 ? (
          <CostChart
            projections={projections}
            routingRecommendation={recommendation}
          />
        ) : (
          <div
            style={{
              padding: "48px",
              textAlign: "center",
              fontFamily: FONT.ui,
              fontSize: 14,
              color: T.t3,
            }}
          >
            {isLoading
              ? "Generating cost projections..."
              : "Click Generate Projection to see cost estimates at 1x, 10x, and 100x scale."}
          </div>
        )}
      </div>
    </PageTransition>
  );
}
