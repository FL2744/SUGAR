import { useEffect, useMemo, useState, type FormEvent } from "react";
import { isTauri } from "@tauri-apps/api/core";
import type { ApiWorkspace } from "./bridge";
import { EmptyState, Spinner, StatusPill, relativeTime } from "./ui";

export function ProjectsPage({ projects, currentId, loading, onOpen, onCreate, onOpenFolder, onRefresh, advanced, createSignal }: {
  projects: ApiWorkspace[]; currentId: string; loading: boolean; advanced: boolean; createSignal: number;
  onOpen: (project: ApiWorkspace) => void; onCreate: (name: string, question: string) => Promise<void>; onOpenFolder: () => void; onRefresh: () => void;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("");
  useEffect(() => { if (createSignal > 0) setCreating(true); }, [createSignal]);
  const shown = useMemo(() => projects.filter((p) => `${p.name} ${p.research_question || ""} ${p.description || ""}`.toLowerCase().includes(filter.toLowerCase())), [projects, filter]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try { await onCreate(name.trim(), question.trim()); setCreating(false); setName(""); setQuestion(""); } finally { setBusy(false); }
  };

  return (
    <section className="page-content projects-page">
      <div className="page-heading compact-heading">
        <div><div className="eyebrow">PROJECTS <span className="eyebrow-line" /></div><h1>Your research projects</h1><p>Each project keeps its request, plans, runs, sources, translations, and history together.</p></div>
        <div className="run-controls">
          {isTauri() && <button className="button button-secondary" onClick={onOpenFolder}>Open folder…</button>}
          <button className="button button-primary button-large" onClick={() => setCreating(true)} aria-label="Create a new project"><span aria-hidden="true">＋</span> New project</button>
        </div>
      </div>

      {creating && (
        <form className="panel new-project-form" onSubmit={(event) => void submit(event)}>
          <div className="panel-heading"><div><span className="eyebrow">NEW PROJECT</span><h3>Name your project</h3></div></div>
          <div className="form-stack">
            <label className="field-block"><span>Project name <em>Required</em></span><input autoFocus value={name} maxLength={120} onChange={(event) => setName(event.target.value)} placeholder="e.g. Democracy in the Middle East" /></label>
            <label className="field-block"><span>Research question</span><input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Optional — you can describe it in your own words on the Research page" /></label>
            <div className="preview-actions"><button className="button button-primary" type="submit" disabled={!name.trim() || busy}>{busy ? <Spinner /> : "Create project"}</button><button className="button button-quiet" type="button" onClick={() => setCreating(false)}>Cancel</button></div>
          </div>
        </form>)}

      <div className="toolbar"><div className="search-field"><span aria-hidden="true">⌕</span><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Find a project" aria-label="Find a project" /></div>
        <button className="button button-quiet button-small" onClick={onRefresh}>↻ Refresh</button><span className="muted">{shown.length} of {projects.length}</span></div>

      {loading && projects.length === 0 && <div className="loading-block"><Spinner /> Loading projects…</div>}
      {!loading && projects.length === 0 && <EmptyState icon="⌂" title="No projects yet" action={<button className="button button-primary" onClick={() => setCreating(true)}>＋ New project</button>}>Create a project to start researching. Nothing is collected until you run a plan.</EmptyState>}
      {shown.length > 0 && (
        <div className="project-table" role="table" aria-label="Projects">
          <div className="project-table-head" role="row"><span role="columnheader">Project</span><span role="columnheader">Research question</span><span role="columnheader">Status</span><span role="columnheader">Last activity</span>{advanced && <span role="columnheader">Runs</span>}<span role="columnheader">Updated</span></div>
          {shown.map((project) => (
            <button key={project.id} role="row" className={`project-row ${project.id === currentId ? "current" : ""}`} onClick={() => onOpen(project)} aria-current={project.id === currentId}>
              <span className="project-name" role="cell"><strong>{project.name}</strong>{project.id === currentId && <small>open</small>}</span>
              <span className="project-question" role="cell" title={project.research_question}>{project.research_question || <em className="muted">No research question yet</em>}</span>
              <span role="cell"><StatusPill status={project.status || "draft"} /></span>
              <span role="cell" className="muted">{relativeTime(project.last_activity || "")}</span>
              {advanced && <span role="cell" className="muted">{project.run_count ?? 0}</span>}
              <span role="cell" className="muted">{project.updated_at ? new Date(project.updated_at).toLocaleDateString() : "—"}</span>
            </button>))}
        </div>)}
    </section>
  );
}
