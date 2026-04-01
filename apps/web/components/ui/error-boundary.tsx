/** ErrorBoundary — catches React errors in subtrees with graceful fallback. */

"use client";

import React, { Component, type ErrorInfo, type ReactNode } from "react";
import { T, FONT } from "@/styles/tokens";

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // In production, log to Sentry
    console.error("ErrorBoundary caught:", error, errorInfo);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;

      return (
        <div
          role="alert"
          style={{
            padding: "24px",
            borderRadius: "8px",
            backgroundColor: T.dangerDim,
            border: `1px solid rgba(196,74,74,0.2)`,
            textAlign: "center",
          }}
        >
          <div style={{ fontFamily: FONT.ui, fontSize: 14, fontWeight: 500, color: T.danger, marginBottom: 8 }}>
            Something went wrong
          </div>
          <div style={{ fontFamily: FONT.data, fontSize: 12, color: T.t3, marginBottom: 12 }}>
            {this.state.error?.message ?? "An unexpected error occurred"}
          </div>
          <button
            type="button"
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: "6px 16px", borderRadius: "4px", border: `1px solid ${T.b2}`,
              backgroundColor: "transparent", color: T.t2, fontFamily: FONT.ui,
              fontSize: 12, cursor: "pointer",
            }}
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
