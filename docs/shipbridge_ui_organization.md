# ShipBridge Frontend UI: Organization (Manager/Admin) Perspective

## 1. Introduction

This document outlines the proposed frontend User Interface (UI) for ShipBridge from the perspective of an **Organization**, typically a Manager, Team Lead, or Administrator. The UI is designed to provide a high-level overview of all projects, enforce governance policies, monitor compliance, manage billing, and provide insights into the overall health and progress of AI agent initiatives across the organization. The focus is on strategic oversight, risk management, and resource allocation.

## 2. Organization Dashboard Overview

The Organization dashboard will offer a centralized view, aggregating data from all projects and teams within the tenant. It prioritizes summary metrics, alerts, and access to governance tools.

### 2.1. Layout and Navigation

*   **Sidebar**: Similar to the End User view, but with additional or elevated access to organization-specific sections:
    *   **Overview**: Aggregated view of all projects, overall readiness, and key organizational metrics.
    *   **Projects**: A list of all projects across teams, with filtering and search capabilities.
    *   **Teams/Users**: Management of user roles, permissions, and team structures.
    *   **Governance**: Access to audit logs, HITL gates, and compliance reporting.
    *   **Billing**: Overview of subscription, usage, and cost projections.
    *   **Settings**: Organization-wide configurations, security policies, and integrations.
*   **Header**: A top header bar will include:
    *   **Organization Switcher**: For managing multiple organizational tenants (if applicable).
    *   **Global Alerts**: Notifications for critical events across all projects (e.g., failed deployments, compliance breaches, high-risk assessments).
    *   **Quick Actions**: Buttons for common administrative tasks, such as "Generate Compliance Report" or "Review HITL Gates".

### 2.2. Overview Tab

This tab provides a strategic summary of the organization's AI agent portfolio.

*   **Overall Readiness Score**: A prominent display of the aggregated readiness score across all active projects, potentially weighted by project criticality. This could be a larger ScoreArc or a similar visual indicator.
*   **Project Health Summary**: A table or card-based view listing all projects, showing:
    *   Project Name, Team, Last Assessment Score, Current Deployment Stage, and overall Status.
    *   Quick links to drill down into individual project dashboards.
*   **Key Performance Indicators (KPIs)**: Charts and graphs visualizing:
    *   **Average Readiness Score Trend**: Historical performance of project readiness.
    *   **Deployment Success Rate**: Percentage of successful deployments vs. rollbacks.
    *   **Total Active Projects**: Number of projects currently being managed.
    *   **Connector Health Summary**: Overview of connected integrations and any unhealthy connectors.
*   **Top 5 Organizational Gaps**: Aggregated view of the most common or severe issues across all projects, derived from individual project gap reports.

## 3. Governance and Compliance

### 3.1. Audit Logs

*   **Immutable Audit Trail**: A dedicated view displaying a comprehensive, immutable log of all agent actions, LLM decisions, state changes, and user interactions across all projects.
    *   Filters for project, user, action type, and date range.
    *   Detailed view of each log entry, including request/response metadata, `tenant_id`, and `trace_id`.
*   **Search and Export**: Capabilities to search through audit logs and export them for external analysis or compliance audits.

### 3.2. Human-in-the-Loop (HITL) Gates

*   **Pending Approvals**: A dashboard section listing all active HITL gates requiring human intervention.
    *   Details include: `gate_id`, triggering event, associated project, and proposed action.
    *   "Approve" / "Reject" buttons with an option to add comments.
*   **Notification Configuration**: Settings to configure Slack webhooks and email notifications for HITL gate triggers.

### 3.3. Compliance Reporting

*   **Compliance PDF Generator**: A feature to generate a structured compliance report (as described in the build plan).
    *   Options to select projects or teams for the report.
    *   Report includes: cover page, 5-pillar scorecard, audit trail summary, deployment history, and GDPR/SOC2 checklist status.
    *   Download button for the generated PDF.
*   **GDPR/SOC2 Checklist**: A configurable checklist to track compliance status across projects, with pass/fail indicators and evidence links.

## 4. Billing and Usage

### 4.1. Subscription Management

*   **Current Plan Overview**: Displays the organization's current subscription plan (Free, Pro, Enterprise).
*   **Usage Metrics**: Detailed breakdown of usage for key metered items:
    *   Number of active projects.
    *   Number of connected connectors.
    *   Number of assessments run per month.
    *   Token consumption estimates (if applicable).
*   **Upgrade/Downgrade Options**: Clear call-to-action buttons for changing subscription plans, integrating with Stripe Checkout.
*   **Billing History**: Access to past invoices and payment information.

### 4.2. Cost Projections

*   **Production Cost Projection**: Visualizations showing projected costs at different scales (1x, 10x, 100x) based on current usage and model routing optimization.
*   **Cost Breakdown Chart**: Per-model breakdown of LLM costs, helping managers understand spending patterns.

## 5. Team and User Management

*   **User Directory**: List of all users within the organization, with roles and permissions.
*   **Role-Based Access Control (RBAC)**: Interface to define and assign roles (e.g., Admin, Manager, Developer) with granular permissions for project access, governance actions, and billing.
*   **Team Management**: Create and manage teams, assigning projects and users to specific teams for better organization and reporting.

## 6. User Experience Principles

*   **Strategic Overview**: Providing high-level, actionable insights for decision-makers.
*   **Transparency**: Clear visibility into project health, compliance status, and resource usage.
*   **Control**: Empowering administrators to enforce policies and manage resources effectively.
*   **Scalability**: Designing for growth, accommodating an increasing number of projects and users.
*   **Security**: Ensuring secure access and data handling, reflecting the multi-tenancy architecture.

This UI design aims to provide organizational stakeholders with the necessary tools and insights to effectively oversee their AI agent development lifecycle, ensuring compliance, managing costs, and driving successful outcomes across their teams. [1] [2] [3]
