/** Framer Motion slideUp page transition wrapper. */

"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";

interface PageTransitionProps {
  children: React.ReactNode;
  /** Unique key for AnimatePresence to track page changes */
  pageKey: string;
}

// Module-level variants — never inline per CLAUDE.md §4.2
const PAGE_VARIANTS = {
  initial: { opacity: 0, y: 12 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

const PAGE_TRANSITION = {
  type: "spring" as const,
  stiffness: 300,
  damping: 30,
};

const PageTransition = React.memo(function PageTransition({ children, pageKey }: PageTransitionProps) {
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={pageKey}
        variants={PAGE_VARIANTS}
        initial="initial"
        animate="animate"
        exit="exit"
        transition={PAGE_TRANSITION}
        style={{ flex: 1 }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  );
});

export default PageTransition;
