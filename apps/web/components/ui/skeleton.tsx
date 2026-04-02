/** Skeleton loading states — match final layout dimensions to prevent shift. */

"use client";

import React from "react";
import { T } from "@/styles/tokens";

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: number;
}

const Skeleton = React.memo(function Skeleton({
  width = "100%",
  height = 16,
  borderRadius = 4,
}: SkeletonProps) {
  return (
    <div
      style={{
        width,
        height,
        borderRadius,
        backgroundColor: T.s3,
        animation: "pulse 1.5s ease-in-out infinite",
      }}
    />
  );
});

/** Skeleton matching a PillarCard layout. */
const PillarCardSkeleton = React.memo(function PillarCardSkeleton() {
  return (
    <div style={{
      padding: 16, borderRadius: 8, backgroundColor: T.s2,
      border: `1px solid ${T.b1}`, minWidth: 180, flex: 1,
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 12 }}>
        <Skeleton width={60} height={10} />
        <Skeleton width={40} height={16} borderRadius={4} />
      </div>
      <Skeleton width={50} height={28} />
      <div style={{ marginTop: 10 }}>
        <Skeleton width="100%" height={3} borderRadius={2} />
      </div>
      <div style={{ marginTop: 10 }}>
        <Skeleton width="80%" height={10} />
      </div>
    </div>
  );
});

/** Skeleton matching the ScoreArc + summary row. */
const ScoreSummarySkeleton = React.memo(function ScoreSummarySkeleton() {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 32, padding: 24,
      backgroundColor: T.s1, borderRadius: 8, border: `1px solid ${T.b0}`,
    }}>
      <Skeleton width={140} height={140} borderRadius={70} />
      <div style={{ flex: 1 }}>
        <Skeleton width={200} height={18} />
        <div style={{ marginTop: 8 }}><Skeleton width={300} height={13} /></div>
        <div style={{ display: "flex", gap: 20, marginTop: 16 }}>
          <Skeleton width={60} height={16} />
          <Skeleton width={80} height={16} />
          <Skeleton width={70} height={16} />
        </div>
      </div>
    </div>
  );
});

/** Skeleton for an event log row. */
const EventRowSkeleton = React.memo(function EventRowSkeleton() {
  return (
    <div style={{
      display: "grid", gridTemplateColumns: "80px 120px 1fr 100px 100px",
      padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
    }}>
      <Skeleton width={50} height={12} />
      <Skeleton width={80} height={12} />
      <Skeleton width={120} height={12} />
      <Skeleton width={60} height={16} borderRadius={4} />
      <Skeleton width={70} height={10} />
    </div>
  );
});

export { Skeleton, PillarCardSkeleton, ScoreSummarySkeleton, EventRowSkeleton };
export default Skeleton;
