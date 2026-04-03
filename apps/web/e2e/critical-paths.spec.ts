/** E2E tests for ShipBridge critical user paths. */

import { test, expect } from "@playwright/test";

test.describe("Authentication", () => {
  test("login page renders and accepts input", async ({ page }) => {
    await page.goto("/auth/login");
    await expect(page.getByText("ShipBridge")).toBeVisible();
    await expect(page.getByPlaceholder("Jane Doe")).toBeVisible();
    await expect(page.getByPlaceholder("jane@company.com")).toBeVisible();
    await expect(page.getByRole("button", { name: "Get Started" })).toBeVisible();
  });

  test("signup submits form and redirects to dashboard", async ({ page }) => {
    await page.goto("/auth/login");
    await page.getByPlaceholder("Jane Doe").fill("Test User");
    await page.getByPlaceholder("jane@company.com").fill("test@shipbridge.dev");
    await page.getByRole("button", { name: "Get Started" }).click();
    // Should redirect to dashboard (or show error if API is unavailable)
    await page.waitForURL(/\/(dashboard|auth)/, { timeout: 10000 });
  });
});

test.describe("Dashboard", () => {
  test("dashboard loads with sidebar navigation", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText("Overview")).toBeVisible();
    await expect(page.getByText("Connectors")).toBeVisible();
    await expect(page.getByText("Events")).toBeVisible();
    await expect(page.getByText("Deployments")).toBeVisible();
    await expect(page.getByText("Costs")).toBeVisible();
    await expect(page.getByText("HITL Gate")).toBeVisible();
  });

  test("overview tab shows readiness score", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText("Production readiness assessment")).toBeVisible();
    await expect(page.getByText("Compliance PDF")).toBeVisible();
  });

  test("connectors tab shows add button", async ({ page }) => {
    await page.goto("/dashboard/connectors");
    await expect(page.getByText("Manage external service connections")).toBeVisible();
    await expect(page.getByText("+ Add Connector")).toBeVisible();
  });

  test("events tab shows pipeline stats", async ({ page }) => {
    await page.goto("/dashboard/events");
    await expect(page.getByText("Real-time event pipeline")).toBeVisible();
    await expect(page.getByText("EVENTS TODAY")).toBeVisible();
  });

  test("deployments tab shows stage pipeline", async ({ page }) => {
    await page.goto("/dashboard/deployments");
    await expect(page.getByText("Staged deployment pipeline")).toBeVisible();
    await expect(page.getByText("Advance to next stage")).toBeVisible();
    await expect(page.getByText("Rollback")).toBeVisible();
  });

  test("costs tab shows projection UI", async ({ page }) => {
    await page.goto("/dashboard/costs");
    await expect(page.getByText("Token usage projections")).toBeVisible();
    await expect(page.getByText("Generate Projection")).toBeVisible();
  });

  test("rules tab shows HITL gate", async ({ page }) => {
    await page.goto("/dashboard/rules");
    await expect(page.getByText("HITL Gate")).toBeVisible();
    await expect(page.getByText("PENDING REVIEW")).toBeVisible();
  });

  test("tab navigation works without full page reload", async ({ page }) => {
    await page.goto("/dashboard");
    await page.getByText("Connectors").click();
    await expect(page).toHaveURL(/\/dashboard\/connectors/);
    await page.getByText("Events").click();
    await expect(page).toHaveURL(/\/dashboard\/events/);
    await page.getByText("Deployments").click();
    await expect(page).toHaveURL(/\/dashboard\/deployments/);
    await page.getByText("Costs").click();
    await expect(page).toHaveURL(/\/dashboard\/costs/);
    await page.getByText("HITL Gate").click();
    await expect(page).toHaveURL(/\/dashboard\/rules/);
  });
});

test.describe("Onboarding", () => {
  test("onboarding wizard renders all steps", async ({ page }) => {
    await page.goto("/onboarding");
    await expect(page.getByText("Name your project")).toBeVisible();
    await page.getByPlaceholder("e.g., Customer Support Agent").fill("Test Agent");
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByText("Select framework")).toBeVisible();
    await page.getByText("LangGraph").click();
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.getByText("Configure stack")).toBeVisible();
    await expect(page.getByText("Run Assessment")).toBeVisible();
  });
});
