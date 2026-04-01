import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import StageTrack from "@/components/deploy/stage-track";
import CanaryMetrics from "@/components/deploy/canary-metrics";

afterEach(() => {
  cleanup();
});

describe("StageTrack", () => {
  const stages = [
    { name: "sandbox", label: "Sandbox", trafficPct: 0, status: "complete" as const },
    { name: "canary5", label: "Canary 5%", trafficPct: 5, status: "active" as const },
    { name: "canary25", label: "Canary 25%", trafficPct: 25, status: "pending" as const },
    { name: "production", label: "Production", trafficPct: 100, status: "pending" as const },
  ];

  it("renders all 4 stage labels", () => {
    render(<StageTrack stages={stages} />);
    expect(screen.getByText("Sandbox")).toBeInTheDocument();
    expect(screen.getByText("Canary 5%")).toBeInTheDocument();
    expect(screen.getByText("Canary 25%")).toBeInTheDocument();
    expect(screen.getByText("Production")).toBeInTheDocument();
  });

  it("renders traffic percentages", () => {
    render(<StageTrack stages={stages} />);
    expect(screen.getByText("0%")).toBeInTheDocument();
    expect(screen.getByText("5%")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
  });

  it("renders with empty stages", () => {
    render(<StageTrack stages={[]} />);
    // Should render without crashing
  });
});

describe("CanaryMetrics", () => {
  const metrics = [
    { label: "Success Rate", value: "93.2", delta: -2.8, unit: "%" },
    { label: "P95 Latency", value: "285", delta: 35, unit: "ms", invertDelta: true },
    { label: "Cost/Task", value: "$0.021", delta: 0.003, unit: "" },
    { label: "Escalation", value: "5.1", delta: 1.1, unit: "%" },
  ];

  it("renders all KPI labels", () => {
    render(<CanaryMetrics metrics={metrics} health="healthy" />);
    expect(screen.getByText("Success Rate")).toBeInTheDocument();
    expect(screen.getByText("P95 Latency")).toBeInTheDocument();
    expect(screen.getByText("Cost/Task")).toBeInTheDocument();
    expect(screen.getByText("Escalation")).toBeInTheDocument();
  });

  it("renders KPI values", () => {
    render(<CanaryMetrics metrics={metrics} health="healthy" />);
    expect(screen.getByText("93.2")).toBeInTheDocument();
    expect(screen.getByText("285")).toBeInTheDocument();
  });

  it("shows HEALTHY badge", () => {
    render(<CanaryMetrics metrics={metrics} health="healthy" />);
    expect(screen.getByText("HEALTHY")).toBeInTheDocument();
  });

  it("shows REGRESSION badge", () => {
    render(<CanaryMetrics metrics={metrics} health="regression" />);
    expect(screen.getByText("REGRESSION")).toBeInTheDocument();
  });

  it("shows ROLLING BACK badge", () => {
    render(<CanaryMetrics metrics={metrics} health="rollback_in_progress" />);
    expect(screen.getByText("ROLLING BACK")).toBeInTheDocument();
  });
});
