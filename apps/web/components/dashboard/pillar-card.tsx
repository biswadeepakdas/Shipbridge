/** Clickable scoring card with spring physics hover/active states. */

"use client";

import React, { useCallback, useMemo } from "react";
import { motion } from "framer-motion";
import { T, FONT } from "@/styles/tokens";
import MicroBar from "@/components/ui/micro-bar";
import StatusTag from "@/components/ui/status-tag";

interface PillarCardProps {
  pillar: {
    id: string;
    label: string;
    score: number;
    status: "ok" | "warn" | "bad";
    note: string;
  };
  isActive: boolean;
  onClick: (id: string) => void;
}

// REQUIRED — variants at module level, NEVER inline
const SPRING_VARIANTS = {
  idle: { y: 0, boxShadow: "0 0 0 rgba(0,0,0,0)" },
  active: { y: -2, boxShadow: "0 4px 20px rgba(0,0,0,0.4)" },
};

const PillarCard = React.memo(function PillarCard({ pillar, isActive, onClick }: PillarCardProps) {
  const handleClick = useCallback(() => onClick(pillar.id), [pillar.id, onClick]);

  const scoreColor = pillar.score >= 75 ? T.sig : pillar.score >= 50 ? T.warn : T.danger;

  const style = useMemo(
    () => ({
      padding: "16px",
      borderRadius: "8px",
      backgroundColor: isActive ? T.s3 : T.s2,
      border: `1px solid ${isActive ? T.b2 : T.b1}`,
      cursor: "pointer",
      minWidth: "180px",
      flex: 1,
    }),
    [isActive],
  );

  return (
    <motion.div
      style={style}
      onClick={handleClick}
      variants={SPRING_VARIANTS}
      animate={isActive ? "active" : "idle"}
      whileHover={{ y: -1 }}
      transition={{ type: "spring", stiffness: 400, damping: 25 }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <span style={{ fontFamily: FONT.label, fontSize: 11, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em" }}>
          {pillar.label}
        </span>
        <StatusTag status={pillar.status} label={pillar.status} />
      </div>
      <div style={{ fontFamily: FONT.data, fontSize: 28, fontWeight: 500, color: scoreColor, marginBottom: 8 }}>
        {pillar.score}
      </div>
      <MicroBar value={pillar.score} color={scoreColor} />
      <p style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t3, marginTop: 8, lineHeight: 1.4 }}>
        {pillar.note}
      </p>
    </motion.div>
  );
});

export default PillarCard;
