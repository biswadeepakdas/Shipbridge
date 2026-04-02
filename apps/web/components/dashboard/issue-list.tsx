/** Expandable issue list for pillar drill-down. */

"use client";

import React, { useCallback, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { T, FONT } from "@/styles/tokens";

interface Issue {
  title: string;
  evidence: string;
  fix_hint: string;
  severity: string;
  effort_days: number;
}

interface IssueListProps {
  issues: Issue[];
  pillarLabel: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  high: T.danger,
  medium: T.warn,
  low: T.t3,
};

// Module-level variants
const EXPAND_VARIANTS = {
  collapsed: { height: 0, opacity: 0 },
  expanded: { height: "auto", opacity: 1 },
};

const IssueRow = React.memo(function IssueRow({ issue }: { issue: Issue }) {
  const [expanded, setExpanded] = useState(false);

  const toggle = useCallback(() => setExpanded((prev) => !prev), []);

  const severityColor = SEVERITY_COLORS[issue.severity] ?? T.t3;

  return (
    <div
      style={{
        borderBottom: `1px solid ${T.b0}`,
        padding: "12px 0",
      }}
    >
      <button
        onClick={toggle}
        type="button"
        style={{
          display: "flex",
          width: "100%",
          justifyContent: "space-between",
          alignItems: "center",
          background: "none",
          border: "none",
          cursor: "pointer",
          padding: 0,
          textAlign: "left",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1 }}>
          <span
            style={{
              fontFamily: FONT.label,
              fontSize: 10,
              fontWeight: 600,
              color: severityColor,
              textTransform: "uppercase",
              letterSpacing: "0.06em",
              minWidth: 50,
            }}
          >
            {issue.severity}
          </span>
          <span style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t1 }}>
            {issue.title}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t3 }}>
            {issue.effort_days}d
          </span>
          <span style={{ color: T.t3, fontSize: 12, transform: expanded ? "rotate(180deg)" : "rotate(0)", transition: "transform 0.2s" }}>
            ▾
          </span>
        </div>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            variants={EXPAND_VARIANTS}
            initial="collapsed"
            animate="expanded"
            exit="collapsed"
            transition={{ duration: 0.2 }}
            style={{ overflow: "hidden" }}
          >
            <div style={{ padding: "12px 0 4px 58px" }}>
              <div style={{ marginBottom: 8 }}>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase" }}>
                  Evidence
                </span>
                <p style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t2, margin: "2px 0 0" }}>
                  {issue.evidence}
                </p>
              </div>
              <div>
                <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase" }}>
                  Fix
                </span>
                <p style={{ fontFamily: FONT.ui, fontSize: 12, color: T.sig, margin: "2px 0 0" }}>
                  {issue.fix_hint}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

const IssueList = React.memo(function IssueList({ issues, pillarLabel }: IssueListProps) {
  if (issues.length === 0) {
    return (
      <div style={{ padding: "16px 0", textAlign: "center" }}>
        <span style={{ fontFamily: FONT.ui, fontSize: 13, color: T.t3 }}>
          No issues found — {pillarLabel} looks good.
        </span>
      </div>
    );
  }

  return (
    <div style={{ padding: "8px 0" }}>
      <div style={{ fontFamily: FONT.label, fontSize: 11, color: T.t3, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {issues.length} issue{issues.length !== 1 ? "s" : ""} in {pillarLabel}
      </div>
      {issues.map((issue, idx) => (
        <IssueRow key={`${issue.title}-${idx}`} issue={issue} />
      ))}
    </div>
  );
});

export default IssueList;
