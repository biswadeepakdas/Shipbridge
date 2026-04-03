/** Events tab — pipeline stats, live event log, unknown trigger alerts. */

"use client";

import { useMemo } from "react";
import Header from "@/components/dashboard/header";
import PageTransition from "@/components/dashboard/page-transition";
import StatusTag from "@/components/ui/status-tag";
import { T, FONT } from "@/styles/tokens";
import { useApiGet } from "@/hooks/use-api";
import { apiUrl } from "@/lib/api";

interface EventDisplay {
  id: string;
  provider: string;
  eventType: string;
  status: "processed" | "queued_unknown" | "duplicate" | "dead_lettered";
  timestamp: string;
  dedupKey: string;
}

const FALLBACK_STATS = {
  eventsToday: 247,
  dedupRate: 0.032,
  unknownQueueSize: 3,
  dlqSize: 0,
};

const FALLBACK_EVENTS: EventDisplay[] = [
  { id: "e1", provider: "salesforce", eventType: "deal.closed", status: "processed", timestamp: "14:32:01", dedupKey: "sf:opp-123" },
  { id: "e2", provider: "slack", eventType: "message.new", status: "processed", timestamp: "14:31:45", dedupKey: "sl:msg-456" },
  { id: "e3", provider: "hubspot", eventType: "contact.updated", status: "processed", timestamp: "14:31:22", dedupKey: "hs:ct-789" },
  { id: "e4", provider: "trello", eventType: "card_moved", status: "queued_unknown", timestamp: "14:30:58", dedupKey: "tr:card-1" },
  { id: "e5", provider: "stripe", eventType: "payment.success", status: "processed", timestamp: "14:30:30", dedupKey: "st:pi-001" },
  { id: "e6", provider: "salesforce", eventType: "deal.closed", status: "duplicate", timestamp: "14:30:15", dedupKey: "sf:opp-123" },
];

const STATUS_MAP: Record<string, { status: "ok" | "warn" | "bad" | "neutral"; label: string }> = {
  processed: { status: "ok", label: "processed" },
  queued_unknown: { status: "warn", label: "unknown" },
  duplicate: { status: "neutral", label: "deduped" },
  dead_lettered: { status: "bad", label: "failed" },
};

export default function EventsPage() {
  const { data: eventsData } = useApiGet<{
    events: Array<{ id: string; provider: string; event_type: string; status: string; created_at: string; dedup_key: string }>;
    stats: { events_today: number; dedup_rate: number; unknown_queue_size: number; dlq_size: number };
  }>(apiUrl("/api/v1/events"));

  const stats = eventsData?.stats
    ? {
        eventsToday: eventsData.stats.events_today,
        dedupRate: eventsData.stats.dedup_rate,
        unknownQueueSize: eventsData.stats.unknown_queue_size,
        dlqSize: eventsData.stats.dlq_size,
      }
    : FALLBACK_STATS;

  const events: EventDisplay[] = useMemo(() => {
    if (!eventsData?.events) return FALLBACK_EVENTS;
    return eventsData.events.map((e) => ({
      id: e.id,
      provider: e.provider,
      eventType: e.event_type,
      status: e.status as EventDisplay["status"],
      timestamp: new Date(e.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
      dedupKey: e.dedup_key,
    }));
  }, [eventsData]);

  return (
    <PageTransition pageKey="events">
      <Header title="Events" subtitle="Real-time event pipeline" />
      <div style={{ padding: "24px" }}>
        {/* Stats strip */}
        <div style={{ display: "flex", gap: "16px", marginBottom: "24px" }}>
          {[
            { label: "EVENTS TODAY", value: stats.eventsToday.toString(), color: T.t1 },
            { label: "DEDUP RATE", value: `${(stats.dedupRate * 100).toFixed(1)}%`, color: T.t2 },
            { label: "UNKNOWN QUEUE", value: stats.unknownQueueSize.toString(), color: stats.unknownQueueSize > 0 ? T.warn : T.ok },
            { label: "DLQ", value: stats.dlqSize.toString(), color: stats.dlqSize > 0 ? T.danger : T.ok },
          ].map((stat) => (
            <div key={stat.label} style={{
              flex: 1, padding: "16px", backgroundColor: T.s1,
              borderRadius: "8px", border: `1px solid ${T.b0}`,
            }}>
              <div style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
                {stat.label}
              </div>
              <div style={{ fontFamily: FONT.data, fontSize: 22, fontWeight: 500, color: stat.color }}>
                {stat.value}
              </div>
            </div>
          ))}
        </div>

        {/* Unknown trigger alert */}
        {stats.unknownQueueSize > 0 && (
          <div style={{
            padding: "12px 16px", marginBottom: "16px",
            backgroundColor: T.warnDim, borderRadius: "6px",
            border: `1px solid rgba(196,154,60,0.2)`,
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <span style={{ fontFamily: FONT.ui, fontSize: 13, color: T.warn }}>
              {stats.unknownQueueSize} unknown trigger(s) awaiting rule generation
            </span>
            <span style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t3, cursor: "pointer" }}>
              Review drafts →
            </span>
          </div>
        )}

        {/* Event log table */}
        <div style={{
          backgroundColor: T.s1, borderRadius: "8px",
          border: `1px solid ${T.b0}`, overflow: "hidden",
        }}>
          <div style={{
            display: "grid", gridTemplateColumns: "80px 120px 1fr 100px 100px",
            padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
          }}>
            {["TIME", "PROVIDER", "EVENT TYPE", "STATUS", "DEDUP KEY"].map((h) => (
              <span key={h} style={{ fontFamily: FONT.label, fontSize: 10, color: T.t3, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                {h}
              </span>
            ))}
          </div>
          {events.map((evt) => {
            const statusInfo = STATUS_MAP[evt.status] ?? { status: "neutral" as const, label: evt.status };
            return (
              <div key={evt.id} style={{
                display: "grid", gridTemplateColumns: "80px 120px 1fr 100px 100px",
                padding: "10px 16px", borderBottom: `1px solid ${T.b0}`,
              }}>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.t3 }}>{evt.timestamp}</span>
                <span style={{ fontFamily: FONT.ui, fontSize: 12, color: T.t2 }}>{evt.provider}</span>
                <span style={{ fontFamily: FONT.data, fontSize: 12, color: T.t1 }}>{evt.eventType}</span>
                <span><StatusTag status={statusInfo.status} label={statusInfo.label} /></span>
                <span style={{ fontFamily: FONT.data, fontSize: 10, color: T.t4 }}>{evt.dedupKey}</span>
              </div>
            );
          })}
        </div>
      </div>
    </PageTransition>
  );
}
