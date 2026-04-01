# ShipBridge Frontend UI: End User (Developer/Engineer) Perspective

## 1. Introduction

This document outlines the proposed frontend User Interface (UI) for ShipBridge from the perspective of an **End User**, typically a Developer or Engineer. The UI is designed to provide a clear, intuitive, and actionable experience for managing AI agent projects, triggering assessments, integrating with external services, and monitoring deployment pipelines. The focus is on providing immediate feedback, detailed insights, and streamlined workflows to enhance productivity and ensure project readiness.

## 2. Dashboard Overview

The End User dashboard will feature a clean, modern layout with a persistent sidebar for navigation and a dynamic main content area. The primary goal is to present critical information at a glance, with options to drill down into details.

### 2.1. Layout and Navigation

*   **Sidebar**: A left-hand sidebar will provide primary navigation links:
    *   **Overview**: A summary of all projects, their readiness scores, and recent activity.
    *   **Projects**: A list of individual projects with options to create new ones or manage existing ones.
    *   **Connectors**: Management of integrations with external services (e.g., GitHub, Salesforce, Notion).
    *   **Events**: A real-time log of agent events and system activities.
    *   **Deployments**: Monitoring and management of staged deployment workflows.
    *   **Settings**: User-specific preferences, API keys, and account management.
*   **Header**: A top header bar will include:
    *   **Project Switcher**: A dropdown to quickly switch between active projects.
    *   **Readiness Score Pill**: A prominent display of the current project's overall readiness score.
    *   **Action Buttons**: Contextual buttons, such as 
 "Run Assessment" or "Deploy".

### 2.2. Project Overview Tab

This tab provides a high-level summary of the selected project, designed to give the engineer an immediate understanding of its health and readiness.

*   **Readiness ScoreArc**: A large, animated radial chart (as described in the build plan) prominently displaying the overall readiness score, with a clear threshold marker at 75%. The arc color changes based on the score (e.g., red for critical, yellow for warning, green for ready).
*   **Pillar Cards**: Five distinct cards, each representing one of the assessment pillars (Reliability, Cost, Security, Eval, Governance). Each card will show:
    *   The pillar's individual score.
    *   A micro-progress bar (`MicroBar.tsx`) for quick visual comparison.
    *   A status tag (`StatusTag.tsx`) (e.g., "Healthy", "Degraded", "Critical").
    *   A brief summary of the most critical issue within that pillar.
    *   Clicking a pillar card will drill down to a detailed view of issues and remediation steps.
*   **Gap Report Summary**: A concise section highlighting the top 3-5 most impactful issues identified by the assessment, with estimated effort days for remediation. Each issue will be clickable to reveal more details.
*   **Recent Activity Feed**: A chronological list of recent actions related to the project, such as assessment runs, deployments, or connector health changes.

## 3. Project Details and Assessment Workflow

### 3.1. Project Configuration

*   **Project Creation Wizard**: A guided flow for creating new projects, allowing users to:
    *   Name the project.
    *   Select the AI agent framework (e.g., LangGraph, CrewAI, AutoGen).
    *   Provide stack configuration details (e.g., LLM models, external services).
    *   Optionally link to a GitHub repository for automatic framework detection.
*   **Project Settings**: For existing projects, a dedicated section to modify name, description, framework, and stack configuration.

### 3.2. Assessment Execution and Monitoring

*   **Trigger Assessment**: A prominent button on the Project Overview and Project Settings pages to initiate a new assessment run.
*   **Live Assessment Stream**: When an assessment is triggered, a real-time Server-Sent Events (SSE) stream will update the UI, showing:
    *   Pillar-by-pillar scoring progress.
    *   Intermediate scores and issue counts as each pillar is evaluated.
    *   A final summary upon completion, including the overall score and readiness gate status.
*   **Assessment History**: A table listing all past assessment runs for the project, including:
    *   Run ID, date, total score, and status.
    *   Links to view detailed scores and gap reports for each run.
*   **Detailed Gap Report View**: A dedicated page accessible from pillar cards or assessment history, showing:
    *   A ranked list of issues by severity and effort.
    *   For each issue: title, evidence, `fix_hint`, and `effort_days`.
    *   Option to mark issues as resolved or create follow-up tasks.

## 4. Integrations and Connectors

### 4.1. Connector Registry

*   **Connector List**: A dashboard tab displaying all available connectors (e.g., GitHub, Salesforce, Notion, Slack, HubSpot, Stripe, Linear, Airtable, Google Workspace, Postgres, Composio).
*   **Connector Cards**: Each connector will have a card showing:
    *   Its current health status (e.g., "Connected", "Degraded", "Disconnected").
    *   Latency sparkline (if applicable).
    *   Rule version (for Composio-integrated connectors).
    *   An "Authorize" button for OAuth-based connectors, leading to a guided connection flow.
    *   Options to view credentials status, refresh tokens, or revoke access.
*   **Unknown Trigger Alert**: A prominent notification in the Connectors tab if Composio webhooks receive unrecognized triggers, with a link to review draft normalization rules.

### 4.2. Event Log

*   **Real-time Event Stream**: A virtualized table (`EventLogTable.tsx`) displaying a live stream of agent events and system activities.
*   **Filtering and Search**: Options to filter events by type, source, tenant, or search for specific payloads.
*   **Payload Preview**: A monospace preview of event payloads for quick inspection.

## 5. Deployment Workflow

### 5.1. Deployments Tab

This tab provides a visual representation and control panel for the staged deployment pipeline.

*   **Stage Track**: A visual representation (`StageTrack.tsx`) of the 4-stage deployment pipeline (Sandbox → Canary 5% → Canary 25% → Production).
    *   Each stage node will indicate its current status (Pending, Active, Complete, Failed, Rolled Back) with animated progress connectors.
    *   An active stage will have a pulsing indicator.
*   **Canary Metrics Grid**: A 4-KPI grid (`CanaryMetrics.tsx`) displaying key metrics for active canary stages (e.g., task success rate, latency p95, token cost/task, error rate).
    *   Metrics will show delta indicators compared to the baseline (sandbox stage), with colored arrows for improvement/regression.
*   **Health Status Badge**: A clear badge indicating the overall deployment health (e.g., "Healthy", "Regression Detected", "Rollback in Progress").
*   **Deployment History**: A list of past deployments, including:
    *   Deployment ID, duration, and outcome (e.g., "Completed", "Rolled Back", "Blocked by Gate").
    *   Links to view detailed stage metrics and audit logs for each deployment.
*   **Manual Rollback Button**: A button to manually trigger a rollback to a previous stable stage, with a confirmation modal.

## 6. Settings and User Management

*   **API Keys**: Section to generate, manage, and revoke API keys with scoped permissions.
*   **Account Profile**: User profile management, including email, password, and multi-factor authentication settings.
*   **Notifications**: Configuration for email, Slack, or in-app notifications for critical events (e.g., deployment rollback, readiness gate block, unknown Composio triggers).

## 7. User Experience Principles

*   **Clarity and Conciseness**: Presenting complex data in an easy-to-understand format.
*   **Actionability**: Providing clear calls-to-action and direct pathways to resolve issues.
*   **Real-time Feedback**: Utilizing SSE and optimistic UI updates to keep users informed.
*   **Consistency**: Maintaining a consistent design language and interaction patterns across the application.
*   **Performance**: Ensuring fast loading times and smooth interactions, even with large datasets.

This UI design aims to empower developers and engineers with the tools and insights needed to efficiently manage their AI agent projects, ensuring they are production-ready and performant. [1] [2] [3]
