/** Typographic status labels: healthy, degraded, critical, etc. No colored dots. */

"use client";

import React, { useMemo } from "react";
import { T, FONT } from "@/styles/tokens";

type StatusType = "ok" | "warn" | "bad" | "neutral";

interface StatusTagProps {
  status: StatusType;
  label: string;
}

const STATUS_STYLES: Record<StatusType, { color: string; bg: string }> = {
  ok: { color: T.ok, bg: T.okDim },
  warn: { color: T.warn, bg: T.warnDim },
  bad: { color: T.danger, bg: T.dangerDim },
  neutral: { color: T.t2, bg: T.b0 },
};

const StatusTag = React.memo(function StatusTag({ status, label }: StatusTagProps) {
  const { color, bg } = STATUS_STYLES[status];

  const style = useMemo(
    () => ({
      display: "inline-flex",
      alignItems: "center",
      padding: "2px 8px",
      borderRadius: "4px",
      fontSize: "11px",
      fontFamily: FONT.label,
      fontWeight: 600,
      letterSpacing: "0.04em",
      textTransform: "uppercase" as const,
      color,
      backgroundColor: bg,
    }),
    [color, bg],
  );

  return <span style={style}>{label}</span>;
});

export default StatusTag;
