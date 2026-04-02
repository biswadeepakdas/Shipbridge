/** StageTrack — 4-node deployment pipeline with animated progress connector. */

"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import { T, FONT } from "@/styles/tokens";

type StageStatus = "pending" | "active" | "complete" | "failed" | "rolled_back";

interface Stage {
  name: string;
  label: string;
  trafficPct: number;
  status: StageStatus;
}

interface StageTrackProps {
  stages: Stage[];
}

const STATUS_COLORS: Record<StageStatus, string> = {
  pending: T.t4,
  active: T.sig,
  complete: T.ok,
  failed: T.danger,
  rolled_back: T.warn,
};

// Module-level variants
const PULSE_VARIANTS = {
  active: {
    scale: [1, 1.15, 1],
    opacity: [1, 0.7, 1],
    transition: { duration: 2, repeat: Infinity, ease: "easeInOut" },
  },
  idle: { scale: 1, opacity: 1 },
};

const CONNECTOR_VARIANTS = {
  incomplete: { scaleX: 0 },
  complete: { scaleX: 1 },
};

const StageTrack = React.memo(function StageTrack({ stages }: StageTrackProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 0, padding: "24px 0" }}>
      {stages.map((stage, idx) => {
        const color = STATUS_COLORS[stage.status];
        const isActive = stage.status === "active";
        const isComplete = stage.status === "complete";
        const showConnector = idx < stages.length - 1;

        return (
          <React.Fragment key={stage.name}>
            {/* Stage node */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", minWidth: 80 }}>
              <motion.div
                variants={PULSE_VARIANTS}
                animate={isActive ? "active" : "idle"}
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  backgroundColor: isActive ? T.sigDim : isComplete ? T.okDim : T.s3,
                  border: `2px solid ${color}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {isComplete && (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke={T.ok} strokeWidth="2" strokeLinecap="round">
                    <path d="M3 8l3 3 7-7" />
                  </svg>
                )}
                {stage.status === "failed" && (
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={T.danger} strokeWidth="2" strokeLinecap="round">
                    <path d="M3 3l8 8M11 3l-8 8" />
                  </svg>
                )}
                {stage.status === "rolled_back" && (
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke={T.warn} strokeWidth="2" strokeLinecap="round">
                    <path d="M10 4L4 10M4 4v6h6" />
                  </svg>
                )}
                {isActive && (
                  <div style={{ width: 8, height: 8, borderRadius: "50%", backgroundColor: T.sig }} />
                )}
              </motion.div>
              <span style={{
                fontFamily: FONT.label, fontSize: 10, color: isActive ? T.sig : T.t3,
                marginTop: 8, textTransform: "uppercase", letterSpacing: "0.04em", textAlign: "center",
              }}>
                {stage.label}
              </span>
              <span style={{ fontFamily: FONT.data, fontSize: 10, color: T.t4, marginTop: 2 }}>
                {stage.trafficPct}%
              </span>
            </div>

            {/* Connector line */}
            {showConnector && (
              <div style={{ flex: 1, height: 2, backgroundColor: T.b1, position: "relative", minWidth: 40, marginBottom: 28 }}>
                <motion.div
                  variants={CONNECTOR_VARIANTS}
                  initial="incomplete"
                  animate={isComplete ? "complete" : "incomplete"}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    height: "100%",
                    backgroundColor: T.ok,
                    transformOrigin: "left",
                  }}
                />
              </div>
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
});

export default StageTrack;
