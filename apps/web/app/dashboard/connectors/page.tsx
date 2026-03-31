/** Connectors tab — placeholder for Day 11+. */

"use client";

import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import { T, FONT } from "@/styles/tokens";

export default function ConnectorsPage() {
  return (
    <PageTransition pageKey="connectors">
      <Header title="Connectors" subtitle="Manage external service connections" />
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
          NO CONNECTORS YET
        </div>
        <p style={{ fontFamily: FONT.ui, fontSize: 14, color: T.t2, textAlign: "center", maxWidth: 320 }}>
          Connect Salesforce, Slack, Notion, and more to give your agents real-time context.
        </p>
      </div>
    </PageTransition>
  );
}
