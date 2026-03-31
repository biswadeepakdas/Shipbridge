/** Events tab — placeholder for Day 19+. */

"use client";

import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import { T, FONT } from "@/styles/tokens";

export default function EventsPage() {
  return (
    <PageTransition pageKey="events">
      <Header title="Events" subtitle="Real-time event pipeline" />
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
          NO EVENTS YET
        </div>
        <p style={{ fontFamily: FONT.ui, fontSize: 14, color: T.t2, textAlign: "center", maxWidth: 320 }}>
          Events will appear here once connectors are configured and webhooks are active.
        </p>
      </div>
    </PageTransition>
  );
}
