/** Connectors — CRUD management for external service connections. */

"use client";

import { useState, useCallback } from "react";
import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import StatusTag from "@/components/ui/status-tag";
import { T, FONT } from "@/styles/tokens";
import { useApiGet, useApiPost } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";

interface ConnectorOut {
  id: string;
  name: string;
  adapter_type: string;
  auth_type: string;
  is_active: boolean;
  config_json: Record<string, unknown>;
  circuit_breaker: {
    state: string;
    failure_count: number;
    success_count: number;
    last_failure_time: string | null;
  } | null;
  latest_health: {
    status: string;
    latency_ms: number;
    checked_at: string;
  } | null;
  created_at: string;
}

interface TestResult {
  connector_id: string;
  status: string;
  latency_ms: number;
  message: string;
}

interface CreateBody {
  name: string;
  adapter_type: string;
  auth_type?: string;
  config_json?: Record<string, unknown>;
}

const ADAPTER_TYPES = [
  "salesforce", "notion", "slack", "github", "hubspot",
  "stripe", "linear", "airtable", "google_workspace", "postgres_direct",
] as const;

const AUTH_TYPES = ["oauth2", "api_key", "basic"] as const;

const COL_TEMPLATE = "1fr 120px 80px 110px 120px 120px 140px";

export default function ConnectorsPage() {
  const { data: connectors, isLoading, refetch } = useApiGet<ConnectorOut[]>(apiUrl("/api/v1/connectors"));
  const { execute: createConnector, isLoading: isCreating } = useApiPost<ConnectorOut, CreateBody>(apiUrl("/api/v1/connectors"));

  const [showForm, setShowForm] = useState(false);
  const [formName, setFormName] = useState("");
  const [formAdapter, setFormAdapter] = useState<string>(ADAPTER_TYPES[0]);
  const [formAuth, setFormAuth] = useState<string>(AUTH_TYPES[0]);

  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({});
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ msg: string; type: "ok" | "danger" } | null>(null);

  const showFeedback = (msg: string, type: "ok" | "danger" = "ok") => {
    setFeedback({ msg, type });
    setTimeout(() => setFeedback(null), 4000);
  };

  const handleCreate = async () => {
    if (!formName.trim()) return;
    const result = await createConnector({
      name: formName.trim(),
      adapter_type: formAdapter,
      auth_type: formAuth,
    });
    if (result) {
      showFeedback(`Connector "${formName.trim()}" created successfully.`);
      setFormName("");
      setFormAdapter(ADAPTER_TYPES[0]);
      setFormAuth(AUTH_TYPES[0]);
      setShowForm(false);
      refetch();
    }
  };

  const handleTest = useCallback(async (id: string) => {
    setTestingId(id);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
      const headers: HeadersInit = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(apiUrl(`/api/v1/connectors/${id}/test`), {
        method: "POST",
        headers,
      });
      const json = await res.json();
      if (json.data) {
        setTestResults((prev) => ({ ...prev, [id]: json.data }));
        showFeedback(`Test complete: ${json.data.status} (${json.data.latency_ms}ms)`);
      } else {
        showFeedback(json.error?.message ?? "Test failed", "danger");
      }
    } catch {
      showFeedback("Test request failed", "danger");
    } finally {
      setTestingId(null);
      refetch();
    }
  }, [refetch]);

  const handleDelete = useCallback(async (id: string, name: string) => {
    setDeletingId(id);
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("sb_token") : null;
      const headers: HeadersInit = {};
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(apiUrl(`/api/v1/connectors/${id}`), {
        method: "DELETE",
        headers,
      });
      const json = await res.json();
      if (json.data) {
        showFeedback(`Connector "${name}" deleted.`);
        refetch();
      } else {
        showFeedback(json.error?.message ?? "Delete failed", "danger");
      }
    } catch {
      showFeedback("Delete request failed", "danger");
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  }, [refetch]);

  const cbStatusTag = (cb: ConnectorOut["circuit_breaker"]) => {
    if (!cb) return <StatusTag status="neutral" label="n/a" />;
    if (cb.state === "closed") return <StatusTag status="ok" label="closed" />;
    if (cb.state === "half_open") return <StatusTag status="warn" label="half-open" />;
    return <StatusTag status="bad" label={cb.state} />;
  };

  const healthStatusTag = (h: ConnectorOut["latest_health"]) => {
    if (!h) return <StatusTag status="neutral" label="no data" />;
    if (h.status === "healthy") return <StatusTag status="ok" label={`${h.latency_ms}ms`} />;
    if (h.status === "degraded") return <StatusTag status="warn" label={`${h.latency_ms}ms`} />;
    return <StatusTag status="bad" label={h.status} />;
  };

  const list = connectors ?? [];

  const selectStyle = {
    flex: 1,
    padding: "8px 10px",
    borderRadius: "6px",
    border: `1px solid ${T.b1}`,
    backgroundColor: T.s2,
    color: T.t1,
    fontFamily: FONT.ui,
    fontSize: 13,
    outline: "none",
    appearance: "auto" as const,
  };

  const inputStyle = {
    flex: 1,
    padding: "8px 10px",
    borderRadius: "6px",
    border: `1px solid ${T.b1}`,
    backgroundColor: T.s2,
    color: T.t1,
    fontFamily: FONT.ui,
    fontSize: 13,
    outline: "none",
  };

  const smallBtnStyle = (color: string, bg: string, border?: string) => ({
    padding: "5px 10px",
    borderRadius: "5px",
    border: border ? `1px solid ${border}` : "none",
    backgroundColor: bg,
    color,
    fontFamily: FONT.ui,
    fontSize: 11,
    fontWeight: 500,
    cursor: "pointer",
    whiteSpace: "nowrap" as const,
  });

  return (
    <PageTransition pageKey="connectors">
      <Header
        title="Connectors"
        subtitle="Manage external service connections"
        actions={
          <button
            onClick={() => setShowForm((v) => !v)}
            style={{
              padding: "8px 16px",
              borderRadius: "6px",
              border: "none",
              backgroundColor: T.sig,
              color: T.s0,
              fontFamily: FONT.ui,
              fontSize: 13,
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            {showForm ? "Cancel" : "+ Add Connector"}
          </button>
        }
      />
      <div style={{ padding: "24px" }}>
        {/* Feedback banner */}
        {feedback && (
          <div
            style={{
              padding: "10px 16px",
              marginBottom: "16px",
              borderRadius: "6px",
              backgroundColor: feedback.type === "ok" ? T.okDim : T.dangerDim,
              border: `1px solid ${feedback.type === "ok" ? T.ok : T.danger}`,
              fontFamily: FONT.ui,
              fontSize: 13,
              color: feedback.type === "ok" ? T.ok : T.danger,
            }}
          >
            {feedback.msg}
          </div>
        )}

        {/* Add connector form */}
        {showForm && (
          <div
            style={{
              padding: "16px",
              marginBottom: "20px",
              backgroundColor: T.s1,
              borderRadius: "8px",
              border: `1px solid ${T.b0}`,
            }}
          >
            <div
              style={{
                fontFamily: FONT.ui,
                fontSize: 13,
                fontWeight: 500,
                color: T.t1,
                marginBottom: 12,
              }}
            >
              New Connector
            </div>
            <div style={{ display: "flex", gap: "12px", alignItems: "flex-end", flexWrap: "wrap" }}>
              <div style={{ flex: 2, minWidth: 180 }}>
                <label
                  style={{
                    fontFamily: FONT.label,
                    fontSize: 10,
                    color: T.t3,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    display: "block",
                    marginBottom: 4,
                  }}
                >
                  NAME
                </label>
                <input
                  type="text"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  placeholder="My Connector"
                  style={inputStyle}
                />
              </div>
              <div style={{ flex: 1, minWidth: 140 }}>
                <label
                  style={{
                    fontFamily: FONT.label,
                    fontSize: 10,
                    color: T.t3,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    display: "block",
                    marginBottom: 4,
                  }}
                >
                  ADAPTER TYPE
                </label>
                <select
                  value={formAdapter}
                  onChange={(e) => setFormAdapter(e.target.value)}
                  style={selectStyle}
                >
                  {ADAPTER_TYPES.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ flex: 1, minWidth: 120 }}>
                <label
                  style={{
                    fontFamily: FONT.label,
                    fontSize: 10,
                    color: T.t3,
                    textTransform: "uppercase",
                    letterSpacing: "0.06em",
                    display: "block",
                    marginBottom: 4,
                  }}
                >
                  AUTH TYPE
                </label>
                <select
                  value={formAuth}
                  onChange={(e) => setFormAuth(e.target.value)}
                  style={selectStyle}
                >
                  {AUTH_TYPES.map((a) => (
                    <option key={a} value={a}>
                      {a}
                    </option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleCreate}
                disabled={isCreating || !formName.trim()}
                style={{
                  padding: "8px 20px",
                  borderRadius: "6px",
                  border: "none",
                  backgroundColor: !formName.trim() ? T.s3 : T.sig,
                  color: !formName.trim() ? T.t3 : T.s0,
                  fontFamily: FONT.ui,
                  fontSize: 13,
                  fontWeight: 500,
                  cursor: !formName.trim() ? "default" : "pointer",
                  opacity: isCreating ? 0.6 : 1,
                }}
              >
                {isCreating ? "Creating..." : "Create"}
              </button>
            </div>
          </div>
        )}

        {/* Stats strip */}
        <div style={{ display: "flex", gap: "16px", marginBottom: "24px" }}>
          {[
            { label: "TOTAL", value: list.length, color: T.t2 },
            { label: "ACTIVE", value: list.filter((c) => c.is_active).length, color: T.ok },
            { label: "INACTIVE", value: list.filter((c) => !c.is_active).length, color: list.filter((c) => !c.is_active).length > 0 ? T.warn : T.t2 },
          ].map((stat) => (
            <div
              key={stat.label}
              style={{
                flex: 1,
                padding: "16px",
                backgroundColor: T.s1,
                borderRadius: "8px",
                border: `1px solid ${T.b0}`,
              }}
            >
              <div
                style={{
                  fontFamily: FONT.label,
                  fontSize: 10,
                  color: T.t3,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  marginBottom: 4,
                }}
              >
                {stat.label}
              </div>
              <div style={{ fontFamily: FONT.data, fontSize: 22, fontWeight: 500, color: stat.color }}>
                {stat.value}
              </div>
            </div>
          ))}
        </div>

        {/* Loading state */}
        {isLoading && (
          <div
            style={{
              padding: "48px",
              textAlign: "center",
              fontFamily: FONT.ui,
              fontSize: 13,
              color: T.t3,
            }}
          >
            Loading connectors...
          </div>
        )}

        {/* Empty state */}
        {!isLoading && list.length === 0 && (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "48px",
            }}
          >
            <div
              style={{
                fontFamily: FONT.label,
                fontSize: 12,
                color: T.t3,
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                marginBottom: 8,
              }}
            >
              NO CONNECTORS YET
            </div>
            <p
              style={{
                fontFamily: FONT.ui,
                fontSize: 14,
                color: T.t2,
                textAlign: "center",
                maxWidth: 320,
              }}
            >
              Connect Salesforce, Slack, Notion, and more to give your agents real-time context.
            </p>
          </div>
        )}

        {/* Connector table */}
        {!isLoading && list.length > 0 && (
          <div
            style={{
              backgroundColor: T.s1,
              borderRadius: "8px",
              border: `1px solid ${T.b0}`,
              overflow: "hidden",
            }}
          >
            {/* Table title */}
            <div
              style={{
                padding: "12px 16px",
                borderBottom: `1px solid ${T.b0}`,
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
              }}
            >
              <span style={{ fontFamily: FONT.ui, fontSize: 13, fontWeight: 500, color: T.t1 }}>
                All Connectors
              </span>
              <span style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3 }}>
                {list.length} connector{list.length !== 1 ? "s" : ""}
              </span>
            </div>

            {/* Header row */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: COL_TEMPLATE,
                padding: "8px 16px",
                borderBottom: `1px solid ${T.b0}`,
              }}
            >
              {["NAME", "ADAPTER", "STATUS", "CIRCUIT BRK", "HEALTH", "CREATED", "ACTIONS"].map(
                (h) => (
                  <span
                    key={h}
                    style={{
                      fontFamily: FONT.label,
                      fontSize: 10,
                      color: T.t3,
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {h}
                  </span>
                ),
              )}
            </div>

            {/* Data rows */}
            {list.map((c) => (
              <div
                key={c.id}
                style={{
                  display: "grid",
                  gridTemplateColumns: COL_TEMPLATE,
                  padding: "10px 16px",
                  borderBottom: `1px solid ${T.b0}`,
                  alignItems: "center",
                  transition: "background-color 0.15s",
                }}
              >
                {/* Name */}
                <span style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t1, fontWeight: 500 }}>
                  {c.name}
                </span>

                {/* Adapter */}
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.t2 }}>
                  {c.adapter_type}
                </span>

                {/* Status */}
                <span>
                  <StatusTag
                    status={c.is_active ? "ok" : "warn"}
                    label={c.is_active ? "active" : "inactive"}
                  />
                </span>

                {/* Circuit breaker */}
                <span>{cbStatusTag(c.circuit_breaker)}</span>

                {/* Health */}
                <span>{healthStatusTag(c.latest_health)}</span>

                {/* Created */}
                <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t4 }}>
                  {new Date(c.created_at).toLocaleDateString()}
                </span>

                {/* Actions */}
                <span style={{ display: "flex", gap: "6px" }}>
                  <button
                    onClick={() => handleTest(c.id)}
                    disabled={testingId === c.id}
                    style={{
                      ...smallBtnStyle(T.sig, T.sigDim, T.sig),
                      opacity: testingId === c.id ? 0.5 : 1,
                    }}
                  >
                    {testingId === c.id ? "Testing..." : "Test"}
                  </button>

                  {confirmDeleteId === c.id ? (
                    <>
                      <button
                        onClick={() => handleDelete(c.id, c.name)}
                        disabled={deletingId === c.id}
                        style={smallBtnStyle(T.danger, T.dangerDim, T.danger)}
                      >
                        {deletingId === c.id ? "..." : "Confirm"}
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(null)}
                        style={smallBtnStyle(T.t2, "transparent", T.b1)}
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setConfirmDeleteId(c.id)}
                      style={smallBtnStyle(T.danger, "transparent", T.b1)}
                    >
                      Delete
                    </button>
                  )}
                </span>
              </div>
            ))}

            {/* Per-row test result display */}
            {list.map(
              (c) =>
                testResults[c.id] && (
                  <div
                    key={`test-${c.id}`}
                    style={{
                      padding: "8px 16px",
                      borderBottom: `1px solid ${T.b0}`,
                      display: "flex",
                      gap: "16px",
                      alignItems: "center",
                      backgroundColor: T.s2,
                    }}
                  >
                    <span style={{ fontFamily: FONT.ui, fontSize: 11, color: T.t3 }}>
                      Test result for <strong style={{ color: T.t1 }}>{c.name}</strong>:
                    </span>
                    <StatusTag
                      status={testResults[c.id].status === "healthy" ? "ok" : "bad"}
                      label={testResults[c.id].status}
                    />
                    <span style={{ fontFamily: FONT.data, fontSize: 11, color: T.t2 }}>
                      {testResults[c.id].latency_ms}ms
                    </span>
                    <span style={{ fontFamily: FONT.ui, fontSize: 11, color: T.t2, flex: 1 }}>
                      {testResults[c.id].message}
                    </span>
                    <button
                      onClick={() =>
                        setTestResults((prev) => {
                          const next = { ...prev };
                          delete next[c.id];
                          return next;
                        })
                      }
                      style={{
                        background: "none",
                        border: "none",
                        color: T.t3,
                        cursor: "pointer",
                        fontSize: 14,
                      }}
                    >
                      x
                    </button>
                  </div>
                ),
            )}
          </div>
        )}
      </div>
    </PageTransition>
  );
}
