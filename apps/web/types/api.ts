/** Standard API response envelope — mirrors backend APIResponse. */
export type APIResponse<T> = {
  data: T | null;
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  } | null;
  meta: Record<string, unknown>;
};

/* ─── Domain types ─────────────────────────────────────────── */

export interface Issue {
  title: string;
  evidence: string;
  fix_hint: string;
  severity: "high" | "medium" | "low";
  effort_days: number;
}

export interface PillarScore {
  score: number;
  status: "ok" | "warn" | "bad";
  issues: Issue[];
  note: string;
}

export interface GapReport {
  blockers: Issue[];
  total_issues: number;
  critical_count: number;
  estimated_effort_days: number;
}

export interface AssessmentRunOut {
  id: string;
  project_id: string;
  total_score: number;
  scores_json: Record<string, PillarScore>;
  gap_report_json: GapReport;
  status: string;
  created_at: string;
}

export interface ProjectOut {
  id: string;
  name: string;
  framework: string;
  stack_json: Record<string, unknown>;
  description: string | null;
  repo_url: string | null;
  created_at: string;
}

export interface NormalizationRule {
  rule_id: string;
  app: string;
  trigger: string;
  payload_map: Record<string, unknown>;
  status: "draft" | "active" | "archived";
  version: number;
  created_at: string;
  updated_at: string;
}

export interface RuleListResponse {
  rules: NormalizationRule[];
  unknown_queue_size: number;
}

export interface ConnectorOut {
  id: string;
  name: string;
  adapter_type: string;
  auth_type: string;
  is_active: boolean;
  config_json: Record<string, unknown>;
  circuit_breaker: {
    state: string;
    failure_count: number;
    last_failure_time: number | null;
    last_success_time: number | null;
    total_requests: number;
    total_failures: number;
  } | null;
  latest_health: {
    status: string;
    latency_ms: number;
    checked_at: string;
  } | null;
  created_at: string;
}

export interface EventEntry {
  id: string;
  provider: string;
  event_type: string;
  status: string;
  tenant_id: string | null;
  created_at: string;
  dedup_key: string;
}

export interface ReadinessGateResponse {
  can_deploy: boolean;
  current_score: number;
  target_score: number;
  gap: number;
  remediation_steps: number;
  estimated_days: number;
}

/* ─── Ingestion types ──────────────────────────────────────── */

export interface IngestionSourceOut {
  id: string;
  project_id: string;
  mode: "github_repo" | "runtime_endpoint" | "sdk_instrumentation" | "manifest";
  config_json: Record<string, unknown>;
  status: "pending" | "validating" | "active" | "failed";
  validation_result: Record<string, unknown> | null;
  last_synced_at: string | null;
  created_at: string;
}

export interface RuntimeTraceOut {
  id: string;
  trace_id: string;
  span_id: string;
  operation: string;
  status: "ok" | "error";
  duration_ms: number;
  model: string | null;
  tool_name: string | null;
  error_message: string | null;
  started_at: string;
}

/* ─── Governance types ─────────────────────────────────────── */

export interface HITLGateOut {
  id: string;
  title: string;
  description: string;
  requested_by: string;
  resource_type: string;
  risk_level: string;
  status: "pending" | "approved" | "rejected" | "expired";
  details: Record<string, unknown>;
  requested_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string | null;
}

export interface AuditEntryOut {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  user_id: string | null;
  agent_id: string | null;
  created_at: string;
}

export interface ManifestValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}
