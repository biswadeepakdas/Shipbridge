/** Header component with project context and action buttons. */

"use client";

import React, { useMemo } from "react";
import { T, FONT } from "@/styles/tokens";

interface HeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

const Header = React.memo(function Header({ title, subtitle, actions }: HeaderProps) {
  return (
    <header
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "20px 24px",
        borderBottom: `1px solid ${T.b0}`,
        backgroundColor: T.s1,
      }}
    >
      <div>
        <h1
          style={{
            fontFamily: FONT.ui,
            fontSize: 20,
            fontWeight: 600,
            color: T.t1,
            margin: 0,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            style={{
              fontFamily: FONT.ui,
              fontSize: 13,
              color: T.t3,
              margin: "4px 0 0",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div style={{ display: "flex", gap: "8px" }}>{actions}</div>}
    </header>
  );
});

export default Header;
