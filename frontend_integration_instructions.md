## Frontend Integration Instructions

This document outlines the necessary steps to integrate the ShipBridge frontend dashboard with the newly implemented backend features for the Human-In-The-Loop (HITL) Gate and Compliance PDF generation.

### **1. HITL Gate Integration**

The HITL Gate allows administrators to review and manage normalization rules (draft, active, archived). The frontend should provide a dedicated section, likely within the 'Governance' or 'Rules' area, to display and interact with these rules.

**Required Frontend Changes:**

*   **Rule Listing Page/Component**:
    *   **Endpoint**: `GET /api/v1/rules`
    *   **Description**: Fetch a list of all normalization rules, including their status (draft, active, archived).
    *   **UI**: Display rules in a table or list format. Each rule should show its `app`, `trigger`, `status`, and potentially a summary of `payload_map`.
    *   **Filtering**: Implement filters to view rules by `app` or `status` (e.g., show only 'draft' rules).

*   **Rule Action Buttons (Promote/Archive)**:
    *   **Promote Button**: For rules with `status: "draft"`, display a "Promote to Active" button.
        *   **Endpoint**: `POST /api/v1/rules/promote`
        *   **Payload**: `{"app": "<rule_app>", "trigger": "<rule_trigger>"}`
        *   **Action**: On success, update the rule's status in the UI to "active".
    *   **Archive Button**: For rules with `status: "active"`, display an "Archive" button.
        *   **Endpoint**: `POST /api/v1/rules/archive`
        *   **Payload**: `{"app": "<rule_app>", "trigger": "<rule_trigger>"}`
        *   **Action**: On success, update the rule's status in the UI to "archived".

*   **Schema Drift Monitoring**:
    *   **Endpoint**: `GET /api/v1/rules/schema-drift`
    *   **Description**: Fetch a list of schemas that have drifted from their expected structure.
    *   **UI**: Display these drifted schemas, potentially with a warning or notification, prompting review.

### **2. Compliance PDF Integration**

The Compliance PDF generation allows users to download a detailed report for a specific project.

**Required Frontend Changes:**

*   **Download Button**: On the project details page or within a 'Governance' tab, add a "Download Compliance Report" button.
    *   **Endpoint**: `GET /api/v1/governance/pdf/{project_id}/download`
    *   **Action**: When clicked, trigger a file download for the PDF report. The `project_id` should be dynamically retrieved from the current project context.

### **3. Real-time Updates (WebSockets/SSE) - Placeholder**

While the backend is capable of handling events, the frontend needs to be updated to consume real-time notifications for events like:

*   Completion of a rule generation task.
*   Status updates for Temporal deployment workflows.
*   New events in the `unknown_event_queue`.

This would typically involve setting up a WebSocket connection to a dedicated endpoint (e.g., `/ws` or `/sse`) and updating the UI dynamically based on received messages. This is a more advanced integration and can be tackled after the initial API wiring.

**Example Frontend Code Snippets (Conceptual - React/Next.js)**

```typescript
// Example for fetching rules
import useSWR from 'swr';

function RulesList() {
  const { data, error } = useSWR('/api/v1/rules', fetcher);

  if (error) return <div>Failed to load rules</div>;
  if (!data) return <div>Loading...</div>;

  return (
    <div>
      {data.rules.map(rule => (
        <div key={rule.rule_id}>
          {rule.app}:{rule.trigger} - {rule.status}
          {rule.status === 'draft' && (
            <button onClick={() => promoteRule(rule.app, rule.trigger)}>Promote</button>
          )}
          {rule.status === 'active' && (
            <button onClick={() => archiveRule(rule.app, rule.trigger)}>Archive</button>
          )}
        </div>
      ))}
    </div>
  );
}

// Example for downloading PDF
function ProjectCompliance({ projectId }) {
  const handleDownload = () => {
    window.open(`/api/v1/governance/pdf/${projectId}/download`, '_blank');
  };

  return (
    <button onClick={handleDownload}>Download Compliance Report</button>
  );
}
```

These instructions provide a clear path for the frontend team to integrate with the new backend functionalities. Once these changes are implemented, the ShipBridge dashboard will offer a comprehensive view and control over the platform's governance and operational aspects.
