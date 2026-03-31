/** Deployments tab — placeholder for Day 23+. */

"use client";

import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import { T, FONT } from "@/styles/tokens";

export default function DeploymentsPage() {
  return (
    <PageTransition pageKey="deployments">
      <Header title="Deployments" subtitle="Staged deployment pipeline" />
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "48px",
        }}
      >
        <div
          style={{
            fontFamily: FONT.label,
            fontSize: 12,
            color: T.t3,
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            marginBottom: 8,
          }}
        >
          NO DEPLOYMENTS YET
        </div>
        <p style={{ fontFamily: FONT.ui, fontSize: 14, color: T.t2, textAlign: "center", maxWidth: 320 }}>
          Reach a readiness score of 75 to unlock staged deployment: sandbox → canary → production.
        </p>
      </div>
    </PageTransition>
  );
}
