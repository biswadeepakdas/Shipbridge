/** Overview tab — pillar cards, score arc, and readiness summary. */

"use client";

import { useCallback, useState } from "react";
import { T, FONT } from "@/styles/tokens";
import Header from "@/components/dashboard/header";
import PillarCard from "@/components/dashboard/pillar-card";
import ScoreArc from "@/components/ui/score-arc";
import PageTransition from "@/components/dashboard/page-transition";

const MOCK_PILLARS = [
  { id: "reliability", label: "Reliability", score: 80, status: "ok" as const, note: "Compound accuracy above threshold" },
  { id: "security", label: "Security", score: 60, status: "warn" as const, note: "MCP endpoints need auth review" },
  { id: "eval", label: "Eval", score: 75, status: "ok" as const, note: "CI grader present, baseline captured" },
  { id: "governance", label: "Governance", score: 70, status: "warn" as const, note: "HITL gates not configured" },
  { id: "cost", label: "Cost", score: 75, status: "ok" as const, note: "Model routing optimized for 3 tiers" },
];

export default function OverviewPage() {
  const [activePillar, setActivePillar] = useState<string | null>(null);

  const handlePillarClick = useCallback((id: string) => {
    setActivePillar((prev) => (prev === id ? null : id));
  }, []);

  const totalScore = Math.round(
    MOCK_PILLARS.reduce((sum, p) => sum + p.score, 0) / MOCK_PILLARS.length,
  );

  return (
    <PageTransition pageKey="overview">
      <Header title="Overview" subtitle="Production readiness assessment" />
      <div style={{ padding: "24px" }}>
        {/* Score + summary row */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "32px",
            marginBottom: "32px",
            padding: "24px",
            backgroundColor: T.s1,
            borderRadius: "8px",
            border: `1px solid ${T.b0}`,
          }}
        >
          <ScoreArc score={totalScore} size={140} />
          <div>
            <h2 style={{ fontFamily: FONT.ui, fontSize: 18, fontWeight: 600, color: T.t1, margin: 0 }}>
              {totalScore >= 75 ? "Ready for production" : "Not yet ready"}
            </h2>
            <p style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t2, marginTop: 4 }}>
              {totalScore >= 75
                ? "All pillars meet the minimum threshold. Proceed with staged deployment."
                : `Score ${totalScore}/100 — address blockers in the gap report to reach 75.`}
            </p>
          </div>
        </div>

        {/* Pillar cards grid */}
        <div
          style={{
            display: "flex",
            gap: "12px",
            flexWrap: "wrap",
          }}
        >
          {MOCK_PILLARS.map((pillar) => (
            <PillarCard
              key={pillar.id}
              pillar={pillar}
              isActive={activePillar === pillar.id}
              onClick={handlePillarClick}
            />
          ))}
        </div>
      </div>
    </PageTransition>
  );
}
