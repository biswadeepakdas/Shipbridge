import { describe, it, expect, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import IssueList from "@/components/dashboard/issue-list";

afterEach(() => {
  cleanup();
});

const MOCK_ISSUES = [
  {
    title: "No prompt injection guard",
    evidence: "Agent accepts user input without filtering",
    fix_hint: "Add input sanitization",
    severity: "high",
    effort_days: 2,
  },
  {
    title: "No audit trail",
    evidence: "Actions not logged",
    fix_hint: "Enable audit logging",
    severity: "medium",
    effort_days: 3,
  },
];

describe("IssueList", () => {
  it("renders issue count and pillar label", () => {
    render(<IssueList issues={MOCK_ISSUES} pillarLabel="Security" />);
    expect(screen.getByText(/2 issues in Security/i)).toBeInTheDocument();
  });

  it("renders all issue titles", () => {
    render(<IssueList issues={MOCK_ISSUES} pillarLabel="Security" />);
    expect(screen.getByText("No prompt injection guard")).toBeInTheDocument();
    expect(screen.getByText("No audit trail")).toBeInTheDocument();
  });

  it("shows empty state when no issues", () => {
    render(<IssueList issues={[]} pillarLabel="Reliability" />);
    expect(screen.getByText(/No issues found/)).toBeInTheDocument();
  });

  it("expands issue to show evidence and fix hint on click", async () => {
    const user = userEvent.setup();
    render(<IssueList issues={MOCK_ISSUES} pillarLabel="Security" />);

    // Click the first issue title's parent button
    const buttons = screen.getAllByRole("button");
    await user.click(buttons[0]);

    // Evidence and fix should now be visible
    expect(screen.getByText("Agent accepts user input without filtering")).toBeInTheDocument();
    expect(screen.getByText("Add input sanitization")).toBeInTheDocument();
  });
});
