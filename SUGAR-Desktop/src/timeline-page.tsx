import { useEffect, useState } from "react";
import { research } from "./research-api";
import type { TimelineEvent } from "./research-types";
import { EmptyState, Spinner, formatTime, relativeTime, titleCase } from "./ui";

const LABELS: Record<string, string> = {
  requirement_edited: "Requirement edited", plan_interpreted: "Request interpreted into a plan", plan_edited: "Plan edited", plan_saved: "Plan saved",
  plan_reinterpreted: "Request reinterpreted", plan_rebuilt: "Plan rebuilt", plan_manual: "Plan entered manually", run_started: "Run started", run_completed: "Run completed",
  run_failed: "Run failed", run_cancelled: "Run cancelled", sources_refreshed: "Sources refreshed", results_reprocessed: "Results reprocessed", run_exported: "Run exported",
  settings_changed: "Project settings changed", member_changed: "Member or role changed", note_added: "Note added", item_reviewed: "Item reviewed", finding_coded: "Finding coded",
  research_run: "Legacy operation", workspace_hub_action: "Workspace action",
};

function detail(event: TimelineEvent): string {
  const d = event.details || {};
  switch (event.event_type) {
    case "requirement_edited": return String(d.requirement || "");
    case "run_started": case "run_completed": case "run_failed": case "run_cancelled":
      return `${titleCase(String(d.kind || ""))}${d.summary ? ` — ${String(d.summary)}` : ""}`;
    case "plan_interpreted": case "plan_edited": case "plan_rebuilt": case "plan_reinterpreted": case "plan_saved":
      return `${String(d.topic || "")} · v${String(d.version || "")} · ${String(d.queries || 0)} searches`;
    case "member_changed": return `${String(d.member || "")} · ${String(d.role || "")}`;
    case "settings_changed": return `Changed: ${((d.changed as string[]) || []).join(", ")}`;
    case "research_run": return `${String(d.command || "")} · ${String(d.status || "")}`;
    default: return "";
  }
}

export function TimelinePage({ projectId, refreshKey }: { projectId: string; refreshKey: number }) {
  const [events, setEvents] = useState<TimelineEvent[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!projectId) { setEvents([]); return; }
    let active = true;
    research.timeline(projectId, 300).then((rows) => { if (active) setEvents(rows); }).catch((issue) => { if (active) setError(issue instanceof Error ? issue.message : String(issue)); });
    return () => { active = false; };
  }, [projectId, refreshKey]);
  return (
    <section className="page-content timeline-page">
      <div className="page-heading compact-heading"><div><div className="eyebrow">PROJECT TIMELINE <span className="eyebrow-line" /></div><h1>What has happened in this project.</h1>
        <p>Requirement edits, plan changes, runs, refreshes, settings changes, and contributor changes — in order.</p></div></div>
      {error && <div className="inline-error">{error}</div>}
      {events === null && !error && <div className="loading-block"><Spinner /> Loading timeline…</div>}
      {events && events.length === 0 && <EmptyState icon="↗" title="Nothing yet">Significant changes appear here as you work.</EmptyState>}
      {events && events.length > 0 && (
        <ol className="timeline">{events.map((event) => (
          <li key={event.event_id}><span className="timeline-dot" aria-hidden="true" />
            <div><strong>{LABELS[event.event_type] || titleCase(event.event_type)}</strong><p>{detail(event)}</p></div>
            <time title={event.occurred_at}>{relativeTime(event.occurred_at)}<small>{formatTime(event.occurred_at)} · {event.actor}</small></time></li>))}</ol>)}
    </section>
  );
}
