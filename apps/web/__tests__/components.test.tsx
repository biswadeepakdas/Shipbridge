import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import StatusTag from "@/components/ui/status-tag";
import MicroBar from "@/components/ui/micro-bar";
import ScoreArc from "@/components/ui/score-arc";
import Header from "@/components/dashboard/header";

afterEach(() => {
  cleanup();
});

describe("StatusTag", () => {
  it("renders with correct label", () => {
    render(<StatusTag status="ok" label="healthy" />);
    expect(screen.getByText("healthy")).toBeInTheDocument();
  });

  it("renders warn status", () => {
    render(<StatusTag status="warn" label="degraded" />);
    expect(screen.getByText("degraded")).toBeInTheDocument();
  });

  it("renders bad status", () => {
    render(<StatusTag status="bad" label="critical" />);
    expect(screen.getByText("critical")).toBeInTheDocument();
  });
});

describe("MicroBar", () => {
  it("renders with correct aria attributes", () => {
    render(<MicroBar value={65} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "65");
    expect(bar).toHaveAttribute("aria-valuemin", "0");
    expect(bar).toHaveAttribute("aria-valuemax", "100");
  });

  it("clamps values above 100", () => {
    render(<MicroBar value={150} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "100");
  });

  it("clamps values below 0", () => {
    render(<MicroBar value={-10} />);
    const bar = screen.getByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "0");
  });
});

describe("ScoreArc", () => {
  it("renders score number", () => {
    render(<ScoreArc score={72} />);
    expect(screen.getByText("72")).toBeInTheDocument();
  });

  it("renders READINESS label", () => {
    render(<ScoreArc score={80} />);
    expect(screen.getByText("READINESS")).toBeInTheDocument();
  });

  it("clamps score to 0-100 range", () => {
    render(<ScoreArc score={110} />);
    expect(screen.getByText("100")).toBeInTheDocument();
  });
});

describe("Header", () => {
  it("renders title", () => {
    render(<Header title="Overview" />);
    expect(screen.getByText("Overview")).toBeInTheDocument();
  });

  it("renders subtitle when provided", () => {
    render(<Header title="Overview" subtitle="Production readiness" />);
    expect(screen.getByText("Production readiness")).toBeInTheDocument();
  });

  it("renders action buttons when provided", () => {
    render(<Header title="Test" actions={<button>Export</button>} />);
    expect(screen.getByText("Export")).toBeInTheDocument();
  });
});
