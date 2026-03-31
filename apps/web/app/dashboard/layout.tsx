/** Dashboard layout with sidebar navigation — wraps all dashboard tabs. */

"use client";

import { T } from "@/styles/tokens";
import Sidebar from "@/components/dashboard/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: "flex", minHeight: "100vh", backgroundColor: T.s0 }}>
      <Sidebar projectName="Customer Support Agent" readinessScore={72} />
      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {children}
      </main>
    </div>
  );
}
