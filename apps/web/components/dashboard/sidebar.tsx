/** Sidebar layout with navigation, project switcher, and readiness score pill. */

"use client";

import React, { useMemo } from "react";
import { usePathname } from "next/navigation";
import { T, FONT } from "@/styles/tokens";
import NavItem from "@/components/ui/nav-item";

const NAV_ITEMS = [
  {
    href: "/dashboard",
    label: "Overview",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <rect x="2" y="2" width="5.5" height="5.5" rx="1" />
        <rect x="10.5" y="2" width="5.5" height="5.5" rx="1" />
        <rect x="2" y="10.5" width="5.5" height="5.5" rx="1" />
        <rect x="10.5" y="10.5" width="5.5" height="5.5" rx="1" />
      </svg>
    ),
  },
  {
    href: "/dashboard/connectors",
    label: "Connectors",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <circle cx="9" cy="9" r="3" />
        <path d="M9 2v4M9 12v4M2 9h4M12 9h4" />
      </svg>
    ),
  },
  {
    href: "/dashboard/events",
    label: "Events",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <path d="M3 14l3-4 3 2 3-5 3 3" />
        <path d="M2 16h14" />
      </svg>
    ),
  },
  {
    href: "/dashboard/deployments",
    label: "Deployments",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <path d="M9 2l6 4v6l-6 4-6-4V6z" />
        <path d="M9 10V2M9 10l6-4M9 10l-6-4" />
      </svg>
    ),
  },
  {
    href: "/dashboard/rules",
    label: "HITL Gate",
    icon: (
      <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round">
        <path d="M9 2v5M9 11v5" />
        <circle cx="9" cy="9" r="2.5" />
        <path d="M2 9h4.5M11.5 9H16" />
      </svg>
    ),
  },
];

interface SidebarProps {
  projectName?: string;
  readinessScore?: number;
}

const Sidebar = React.memo(function Sidebar({
  projectName = "ShipBridge",
  readinessScore,
}: SidebarProps) {
  const pathname = usePathname();

  const scoreColor = readinessScore
    ? readinessScore >= 75 ? T.sig : readinessScore >= 50 ? T.warn : T.danger
    : T.t3;

  return (
    <aside
      style={{
        width: 220,
        minHeight: "100vh",
        backgroundColor: T.s1,
        borderRight: `1px solid ${T.b0}`,
        display: "flex",
        flexDirection: "column",
        padding: "16px 12px",
      }}
    >
      {/* Logo */}
      <div style={{ padding: "0 8px 16px", borderBottom: `1px solid ${T.b0}` }}>
        <span style={{ fontFamily: FONT.ui, fontSize: 16, fontWeight: 600, color: T.sig }}>
          ShipBridge
        </span>
      </div>

      {/* Project switcher */}
      <div
        style={{
          margin: "16px 0",
          padding: "8px 10px",
          backgroundColor: T.s2,
          borderRadius: "6px",
          border: `1px solid ${T.b0}`,
        }}
      >
        <div style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t3, marginBottom: 2 }}>
          PROJECT
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontFamily: FONT.ui, fontSize: 13, fontWeight: 500, color: T.t1 }}>
            {projectName}
          </span>
          {readinessScore !== undefined && (
            <span
              style={{
                fontFamily: FONT.data,
                fontSize: 11,
                fontWeight: 500,
                color: scoreColor,
                backgroundColor: T.s3,
                padding: "2px 6px",
                borderRadius: "4px",
              }}
            >
              {readinessScore}
            </span>
          )}
        </div>
      </div>

      {/* Navigation */}
      <nav style={{ display: "flex", flexDirection: "column", gap: "2px", flex: 1 }}>
        {NAV_ITEMS.map((item) => (
          <NavItem
            key={item.href}
            href={item.href}
            label={item.label}
            icon={item.icon}
            isActive={pathname === item.href}
          />
        ))}
      </nav>

      {/* Version */}
      <div style={{ padding: "12px 8px 0", borderTop: `1px solid ${T.b0}` }}>
        <span style={{ fontFamily: FONT.data, fontSize: 10, color: T.t4 }}>
          v0.1.0
        </span>
      </div>
    </aside>
  );
});

export default Sidebar;
