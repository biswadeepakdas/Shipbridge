/** Dashboard layout with sidebar navigation — wraps all dashboard tabs. */

"use client";

import { useMemo } from "react";
import { T } from "@/styles/tokens";
import Sidebar from "@/components/dashboard/sidebar";
import { useApiGet } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";
import type { ProjectOut, AssessmentRunOut } from "@/types/api";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data: projects } = useApiGet<ProjectOut[]>(apiUrl("/api/v1/projects"));
  const projectId = projects?.[0]?.id;
  const projectName = projects?.[0]?.name ?? "ShipBridge";

  const { data: assessments } = useApiGet<AssessmentRunOut[]>(
    projectId ? apiUrl(`/api/v1/projects/${projectId}/assessments`) : null
  );
  const readinessScore = assessments?.[0]?.total_score ?? 0;

  return (
    <div style={{ display: "flex", minHeight: "100vh", backgroundColor: T.s0 }}>
      <Sidebar projectName={projectName} readinessScore={readinessScore} />
      <main style={{ flex: 1, display: "flex", flexDirection: "column" }}>
        {children}
      </main>
    </div>
  );
}
