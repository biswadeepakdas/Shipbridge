import { describe, it, expect, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ErrorBoundary from "@/components/ui/error-boundary";
import { Skeleton, PillarCardSkeleton, ScoreSummarySkeleton, EventRowSkeleton } from "@/components/ui/skeleton";

afterEach(() => {
  cleanup();
});

// --- ErrorBoundary ---

function ThrowingChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error("Test error");
  return <div>Normal content</div>;
}

describe("ErrorBoundary", () => {
  it("renders children when no error", () => {
    render(
      <ErrorBoundary>
        <div>Safe content</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText("Safe content")).toBeInTheDocument();
  });

  it("renders fallback on error", () => {
    // Suppress console.error for this test
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Test error")).toBeInTheDocument();
    spy.mockRestore();
  });

  it("renders custom fallback when provided", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary fallback={<div>Custom fallback</div>}>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Custom fallback")).toBeInTheDocument();
    spy.mockRestore();
  });

  it("has a Try again button", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText("Try again")).toBeInTheDocument();
    spy.mockRestore();
  });
});

// --- Skeletons ---

describe("Skeleton", () => {
  it("renders with default props", () => {
    const { container } = render(<Skeleton />);
    const el = container.firstChild as HTMLElement;
    expect(el).toBeTruthy();
    expect(el.style.width).toBe("100%");
  });

  it("renders with custom dimensions", () => {
    const { container } = render(<Skeleton width={200} height={40} />);
    const el = container.firstChild as HTMLElement;
    expect(el.style.width).toBe("200px");
    expect(el.style.height).toBe("40px");
  });
});

describe("PillarCardSkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<PillarCardSkeleton />);
    expect(container.firstChild).toBeTruthy();
  });
});

describe("ScoreSummarySkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<ScoreSummarySkeleton />);
    expect(container.firstChild).toBeTruthy();
  });
});

describe("EventRowSkeleton", () => {
  it("renders without crashing", () => {
    const { container } = render(<EventRowSkeleton />);
    expect(container.firstChild).toBeTruthy();
  });
});
