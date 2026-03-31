/** Inline progress bar for score visualization within pillar cards. Always 3px height, 2px border-radius. */

"use client";

import React, { useMemo } from "react";
import { T } from "@/styles/tokens";

interface MicroBarProps {
  /** Score value 0–100 */
  value: number;
  /** Color override, defaults to sig accent */
  color?: string;
}

const MicroBar = React.memo(function MicroBar({ value, color = T.sig }: MicroBarProps) {
  const clampedValue = Math.max(0, Math.min(100, value));

  const containerStyle = useMemo(
    () => ({
      width: "100%",
      height: "3px",
      borderRadius: "2px",
      backgroundColor: T.b1,
      overflow: "hidden" as const,
    }),
    [],
  );

  const fillStyle = useMemo(
    () => ({
      width: `${clampedValue}%`,
      height: "100%",
      borderRadius: "2px",
      backgroundColor: color,
      transition: "width 0.4s ease",
    }),
    [clampedValue, color],
  );

  return (
    <div style={containerStyle} role="progressbar" aria-valuenow={clampedValue} aria-valuemin={0} aria-valuemax={100}>
      <div style={fillStyle} />
    </div>
  );
});

export default MicroBar;
