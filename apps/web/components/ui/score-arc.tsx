/** Radial score ring with 75% threshold marker and animated fill. */

"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import { T, FONT } from "@/styles/tokens";

interface ScoreArcProps {
  /** Score value 0–100 */
  score: number;
  /** Size in pixels */
  size?: number;
  /** Stroke width */
  strokeWidth?: number;
}

const THRESHOLD = 75;

const ScoreArc = React.memo(function ScoreArc({
  score,
  size = 120,
  strokeWidth = 8,
}: ScoreArcProps) {
  const clampedScore = Math.max(0, Math.min(100, score));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;

  const scoreColor = clampedScore >= THRESHOLD ? T.sig : clampedScore >= 50 ? T.warn : T.danger;

  // Threshold marker position (75% around the circle)
  const thresholdAngle = (THRESHOLD / 100) * 360 - 90;
  const thresholdRad = (thresholdAngle * Math.PI) / 180;
  const markerX = center + (radius * Math.cos(thresholdRad));
  const markerY = center + (radius * Math.sin(thresholdRad));

  const scoreOffset = circumference - (clampedScore / 100) * circumference;

  const containerStyle = useMemo(
    () => ({
      position: "relative" as const,
      width: size,
      height: size,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
    }),
    [size],
  );

  return (
    <div style={containerStyle}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        {/* Background track */}
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={T.b1}
          strokeWidth={strokeWidth}
        />
        {/* Score arc */}
        <motion.circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={scoreColor}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: scoreOffset }}
          transition={{ duration: 1, ease: "easeOut" }}
        />
        {/* Threshold marker at 75 */}
        <circle
          cx={markerX}
          cy={markerY}
          r={3}
          fill={T.t3}
        />
      </svg>
      {/* Score number */}
      <div
        style={{
          position: "absolute",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
        }}
      >
        <span
          style={{
            fontSize: size * 0.28,
            fontFamily: FONT.data,
            fontWeight: 500,
            color: scoreColor,
            lineHeight: 1,
          }}
        >
          {clampedScore}
        </span>
        <span
          style={{
            fontSize: 10,
            fontFamily: FONT.label,
            color: T.t3,
            marginTop: 2,
          }}
        >
          READINESS
        </span>
      </div>
    </div>
  );
});

export default ScoreArc;
