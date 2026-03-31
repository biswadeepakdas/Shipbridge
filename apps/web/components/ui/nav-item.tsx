/** Sidebar navigation item with active indicator and SVG icon system. */

"use client";

import React, { useCallback, useMemo } from "react";
import Link from "next/link";
import { T, FONT } from "@/styles/tokens";

interface NavItemProps {
  href: string;
  label: string;
  icon: React.ReactNode;
  isActive: boolean;
}

const NavItem = React.memo(function NavItem({ href, label, icon, isActive }: NavItemProps) {
  const style = useMemo(
    () => ({
      display: "flex",
      alignItems: "center",
      gap: "10px",
      padding: "8px 12px",
      borderRadius: "6px",
      fontSize: "13px",
      fontFamily: FONT.ui,
      fontWeight: isActive ? 500 : 400,
      color: isActive ? T.t1 : T.t2,
      backgroundColor: isActive ? T.sigDim : "transparent",
      borderLeft: isActive ? `2px solid ${T.sig}` : "2px solid transparent",
      transition: "all 0.15s ease",
      textDecoration: "none",
      cursor: "pointer",
    }),
    [isActive],
  );

  return (
    <Link href={href} style={style}>
      <span style={{ display: "flex", alignItems: "center", width: 18, height: 18, color: isActive ? T.sig : T.t3 }}>
        {icon}
      </span>
      <span>{label}</span>
    </Link>
  );
});

export default NavItem;
