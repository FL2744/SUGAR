import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

export function titleCase(value: string) {
  return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatTime(iso: string, withSeconds = false): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", ...(withSeconds ? { second: "2-digit" } : {}) });
}

export function relativeTime(iso: string): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const seconds = Math.round((Date.now() - date.getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days} d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: date.getFullYear() === new Date().getFullYear() ? undefined : "numeric" });
}

export function duration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const seconds = ms / 1000;
  if (seconds < 90) return `${seconds.toFixed(seconds < 10 ? 1 : 0)} s`;
  return `${Math.floor(seconds / 60)} min ${Math.round(seconds % 60)} s`;
}

export const LANGUAGE_NAMES: Record<string, string> = {
  en: "English", ar: "Arabic", fa: "Persian", tr: "Turkish", he: "Hebrew", ku: "Kurdish", ur: "Urdu", hi: "Hindi", bn: "Bengali",
  fr: "French", es: "Spanish", pt: "Portuguese", de: "German", it: "Italian", ru: "Russian", uk: "Ukrainian", pl: "Polish", zh: "Chinese",
  ja: "Japanese", ko: "Korean", id: "Indonesian", vi: "Vietnamese", th: "Thai", sw: "Swahili", und: "Unknown", auto: "Automatic",
};
export const languageName = (code: string) => LANGUAGE_NAMES[code] || code.toUpperCase();

export const PLATFORM_LABELS: Record<string, string> = { x: "X", bluesky: "Bluesky", mastodon: "Mastodon", bilibili: "Bilibili", weibo: "Weibo", wechat: "WeChat", wikipedia: "Wikipedia", gdelt: "News (GDELT)", openalex: "Scholarly (OpenAlex)", rss: "News & institution feeds", web: "Websites" };
export const platformLabel = (id: string) => PLATFORM_LABELS[id] || titleCase(id);

export function Pill({ tone = "neutral", children, title }: { tone?: "neutral" | "ok" | "warn" | "error" | "info" | "busy"; children: ReactNode; title?: string }) {
  return <span className={`pill pill-${tone}`} title={title}>{children}</span>;
}

export const STATUS_TONE: Record<string, "neutral" | "ok" | "warn" | "error" | "info" | "busy"> = {
  draft: "neutral", ready: "info", running: "busy", paused: "warn", queued: "busy", cancelling: "warn", completed: "ok",
  completed_with_warnings: "warn", attention: "warn", failed: "error", cancelled: "neutral",
};

export function StatusPill({ status }: { status: string }) {
  const label = status === "completed_with_warnings" ? "Completed with warnings" : titleCase(status || "draft");
  return <Pill tone={STATUS_TONE[status] || "neutral"}>{label}</Pill>;
}

export function Spinner({ label }: { label?: string }) {
  return <span className="spinner" role="status" aria-label={label || "Working"} />;
}

export function EmptyState({ icon = "◌", title, children, action }: { icon?: string; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-block">
      <span className="empty-block-icon" aria-hidden="true">{icon}</span>
      <strong>{title}</strong>
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}

export function Collapsible({ title, hint, defaultOpen = false, children, badge }: { title: string; hint?: string; defaultOpen?: boolean; children: ReactNode; badge?: ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className={`collapsible ${open ? "open" : ""}`}>
      <button type="button" className="collapsible-head" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="collapsible-caret" aria-hidden="true">{open ? "▾" : "▸"}</span>
        <span><strong>{title}</strong>{hint && <small>{hint}</small>}</span>
        {badge}
      </button>
      {open && <div className="collapsible-body">{children}</div>}
    </section>
  );
}

/** A list of short text values (regions, languages, exclusions...) edited as removable chips. */
export function ChipInput({ label, values, onChange, placeholder, hint, suggestions }: {
  label: string; values: string[]; onChange: (next: string[]) => void; placeholder?: string; hint?: string; suggestions?: string[];
}) {
  const [draft, setDraft] = useState("");
  const listId = `chips-${label.replace(/\W+/g, "-").toLowerCase()}`;
  const add = () => {
    const value = draft.trim().replace(/,$/, "");
    if (value && !values.some((existing) => existing.toLowerCase() === value.toLowerCase())) onChange([...values, value]);
    setDraft("");
  };
  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") { event.preventDefault(); add(); }
    else if (event.key === "Backspace" && !draft && values.length) onChange(values.slice(0, -1));
  };
  return (
    <div className="field-block chip-field">
      <span>{label}</span>
      <div className="chip-box">
        {values.map((value) => (
          <span className="chip" key={value}>{value}<button type="button" aria-label={`Remove ${value}`} onClick={() => onChange(values.filter((v) => v !== value))}>×</button></span>
        ))}
        <input value={draft} list={suggestions ? listId : undefined} onChange={(event) => setDraft(event.target.value)} onKeyDown={onKey} onBlur={add} placeholder={values.length ? "" : placeholder} aria-label={label} />
        {suggestions && <datalist id={listId}>{suggestions.map((s) => <option key={s} value={s} />)}</datalist>}
      </div>
      {hint && <small>{hint}</small>}
    </div>
  );
}

export function Segmented<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string; hint?: string }>; onChange: (v: T) => void; label: string }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button type="button" key={option.value} role="radio" aria-checked={value === option.value} className={value === option.value ? "on" : ""} title={option.hint} onClick={() => onChange(option.value)}>{option.label}</button>
      ))}
    </div>
  );
}

export function CopyButton({ text, label = "Copy", className = "button button-quiet button-small" }: { text: string; label?: string; className?: string }) {
  const [done, setDone] = useState(false);
  return (
    <button type="button" className={className} onClick={() => {
      void navigator.clipboard?.writeText(text).then(() => { setDone(true); setTimeout(() => setDone(false), 1500); }).catch(() => undefined);
    }}>{done ? "Copied ✓" : label}</button>
  );
}

type IncompleteRun = { completeness?: { complete?: boolean; incomplete_sources?: string[]; notes?: string[]; sources?: Record<string, { status: string; error: Record<string, unknown> }> } };

/** Which sources could not be collected and why, one row each, with a retry where the caller supports it. */
export function IncompleteNotice({ run, onRetry, busy }: { run: IncompleteRun; onRetry?: (source: string) => void; busy?: boolean }) {
  const rows = run.completeness?.sources || {};
  const bad = run.completeness?.incomplete_sources || [];
  const extra = (run.completeness?.notes || []).filter((note) => !/ was (skipped|not fully collected):/.test(note));
  return (
    <div className="notice notice-warn incomplete-card" role="alert">
      <strong>Some sources could not be collected.</strong> Results cover only part of what you asked for.
      <ul className="incomplete-list">
        {bad.map((name) => {
          const row = rows[name];
          return (
            <li key={name}>
              <div><b>{platformLabel(name)}</b> <Pill tone={row?.status === "skipped" ? "neutral" : "warn"}>{row?.status === "skipped" ? "Skipped" : "Incomplete"}</Pill>
                <span className="muted">{String(row?.error?.message || "See the warnings for details.")}</span></div>
              {onRetry && <button className="button button-secondary button-small" disabled={busy} onClick={() => onRetry(name)}>Retry</button>}
            </li>);
        })}
      </ul>
      {extra.map((note) => <p key={note} className="muted">{note}</p>)}
    </div>
  );
}

export const VERDICTS: Array<{ id: "relevant" | "not_relevant" | "follow_up"; label: string; mark: string; tone: "ok" | "neutral" | "warn" }> = [
  { id: "relevant", label: "Relevant", mark: "✓", tone: "ok" },
  { id: "not_relevant", label: "Not relevant", mark: "✕", tone: "neutral" },
  { id: "follow_up", label: "Follow up", mark: "⚑", tone: "warn" },
];

export function VerdictPill({ verdict }: { verdict: string }) {
  const v = VERDICTS.find((entry) => entry.id === verdict);
  return v ? <Pill tone={v.tone} title={`Marked ${v.label.toLowerCase()}`}>{v.mark} {v.label}</Pill> : null;
}

export type Toast = { id: number; tone: "info" | "ok" | "warn"; text: string; action?: { label: string; run: () => void } };

/** Short, non-blocking confirmations ("Run finished — 14 items"). Polite live region; they dismiss themselves. */
export function ToastHost({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  return (
    <div className="toast-host" role="status" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast ${toast.tone}`}>
          <span>{toast.text}</span>
          {toast.action && <button className="toast-action" onClick={() => { toast.action?.run(); onDismiss(toast.id); }}>{toast.action.label}</button>}
          <button aria-label="Dismiss" onClick={() => onDismiss(toast.id)}>×</button>
        </div>))}
    </div>
  );
}


const paths = {
  overview: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  research: "M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5 M14 3h7v7 M21 3l-11 11 M7 10h2 M7 17h8",
  globe: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c-4 4-4 14 0 18 M12 3c4 4 4 14 0 18",
  history: "M3 11a9 9 0 1 1 2 7 M3 4v7h7 M12 7v5l3 2",
  settings: "m9 3-.6 2.2-2 .9-2-.6-2 3.4L4 10.5v2.9l-1.6 1.5 2 3.4 2-.6 2 .9.6 2.4h4l.6-2.4 2-.9 2 .6 2-3.4-1.6-1.5v-2.9l1.6-1.6-2-3.4-2 .6-2-.9L13 3z M14.5 12a3.5 3.5 0 1 1-7 0 3.5 3.5 0 0 1 7 0",
  search: "M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0 M14.5 14.5 21 21",
  arrow: "M4 12h16 M14 6l6 6-6 6",
  chevron: "m9 5 7 7-7 7",
  check: "m5 12 4 4 10-10",
  close: "m6 6 12 12 M18 6 6 18",
  folder: "M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
  file: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z M14 3v6h6 M8 13h8 M8 17h5",
  link: "m10 13 4-4 M8 16l-1 1a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0 M16 8l1-1a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0",
  upload: "M12 16V3 M7 8l5-5 5 5 M4 15v5h16v-5",
  download: "M12 3v13 M7 11l5 5 5-5 M4 17v4h16v-4",
  plus: "M12 5v14 M5 12h14",
  moon: "M20 15A9 9 0 0 1 9 4 9 9 0 1 0 20 15",
  sun: "M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M12 2v2 M12 20v2 M2 12h2 M20 12h2 M5 5l1.5 1.5 M17.5 17.5 19 19 M5 19l1.5-1.5 M17.5 6.5 19 5",
  shield: "m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z m-4 9 3 3 5-6",
  users: "M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-3a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v3 M2 8a3 3 0 0 1 0 6 M22 8a3 3 0 0 0 0 6",
  spark: "m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5z",
  play: "m8 4 12 8-12 8z",
  layers: "m12 3 10 6-10 6L2 9z M2 13l10 6 10-6 M2 17l10 6 10-6",
  activity: "M2 12h5l3-8 4 16 3-8h5",
  pin: "M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 0 1 14 0 M14 10a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
  info: "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 11v6 M12 7h.01",
  refresh: "M20 7a9 9 0 0 0-15 0l-2 3 M3 4v6h6 M4 17a9 9 0 0 0 15 0l2-3 M15 14h6v6",
  network: "M14 12a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M5 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M23 4a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M5 20a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M23 20a2 2 0 1 1-4 0 2 2 0 0 1 4 0 M5 6l5 4 M14 10l5-4 M5 18l5-4 M14 14l5 4",
};
export type IconName = keyof typeof paths;

export function Icon({ name, size = 20, className = "" }: { name: IconName; size?: number; className?: string }) {
  return <svg className={`ui-icon ${className}`} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><path d={paths[name]} /></svg>;
}

export function BrandMark() {
  return <svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="m20 3 14.7 8.5v17L20 37 5.3 28.5v-17z" stroke="currentColor" strokeWidth="1.5" /><path d="m12 24 8-14 8 14H12Z M12 24l8 6 8-6 M20 10v20" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" /><circle cx="20" cy="10" r="2.3" fill="currentColor" /><circle cx="12" cy="24" r="2.3" fill="currentColor" /><circle cx="28" cy="24" r="2.3" fill="currentColor" /></svg>;
}

export function ResearchGraphic() {
  return <div className="research-graphic" aria-hidden="true"><div className="graphic-grid" /><svg className="graphic-connections" viewBox="0 0 380 230" fill="none"><path d="M96 62h85q20 0 20 20v34 M201 116v47q0 20 20 20h66" stroke="currentColor" strokeWidth="1.5" strokeDasharray="5 5" /><circle cx="201" cy="116" r="6" fill="currentColor" /></svg><div className="graphic-node graphic-source"><Icon name="globe" /><div><small>01 / DISCOVER</small><strong>Public sources</strong></div><span className="graphic-dot" /></div><div className="graphic-node graphic-evidence"><Icon name="layers" /><div><small>02 / CONNECT</small><strong>Source-backed evidence</strong></div></div><div className="graphic-node graphic-review"><Icon name="shield" /><div><small>03 / UNDERSTAND</small><strong>Human insight</strong></div><Icon name="check" size={16} /></div></div>;
}

export function Modal({ open, onClose, labelId, children, className = "" }: { open: boolean; onClose: () => void; labelId: string; children: ReactNode; className?: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (open && dialog.current && !dialog.current.open) {
      dialog.current.showModal();
      dialog.current.querySelector<HTMLElement>("[data-dialog-focus]")?.focus();
    }
    if (!open && dialog.current?.open) dialog.current?.close();
  }, [open]);
  return <dialog ref={dialog} className={`app-dialog ${className}`} aria-labelledby={labelId} onCancel={onClose} onClose={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}><div className="dialog-content">{children}</div></dialog>;
}

export const PROJECT_SECTIONS = [
  { id: "brief", label: "Research brief", icon: "research", detail: "Question & collection plan" },
  { id: "evidence", label: "Evidence", icon: "layers", detail: "Sources, analysis & export" },
  { id: "team", label: "Team & notes", icon: "users", detail: "People & shared context" },
  { id: "monitoring", label: "Monitoring", icon: "activity", detail: "Recurring listening posts" },
] as const;
export type ProjectSection = typeof PROJECT_SECTIONS[number]["id"];

export function ProjectTabs({ active, onChange }: { active: ProjectSection; onChange: (section: ProjectSection) => void }) {
  return <div className="project-tabs" role="tablist" aria-label="Project sections">{PROJECT_SECTIONS.map((section, index) => <button key={section.id} id={`tab-${section.id}`} role="tab" aria-selected={active === section.id} aria-controls={`project-section-${section.id}`} tabIndex={active === section.id ? 0 : -1} onClick={() => onChange(section.id)} onKeyDown={(event) => {
    const offset = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
    if (!offset && !["Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = PROJECT_SECTIONS[event.key === "Home" ? 0 : event.key === "End" ? PROJECT_SECTIONS.length - 1 : (index + offset + PROJECT_SECTIONS.length) % PROJECT_SECTIONS.length];
    onChange(next.id);
    document.getElementById(`tab-${next.id}`)?.focus();
  }}><Icon name={section.icon} /><span><strong>{section.label}</strong><small>{section.detail}</small></span></button>)}</div>;
}

export type QuickAction = { id: string; title: string; detail: string; icon: IconName; run: () => void };

export function CommandPalette({ open, onClose, actions }: { open: boolean; onClose: () => void; actions: QuickAction[] }) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const filtered = actions.filter((item) => `${item.title} ${item.detail}`.toLowerCase().includes(query.toLowerCase().trim()));
  useEffect(() => { if (open) { setQuery(""); setActive(0); input.current?.focus(); } }, [open]);
  useEffect(() => { if (open && filtered[active]) document.getElementById(`quick-action-${filtered[active].id}`)?.scrollIntoView({ block: "nearest" }); }, [active, query, open]);
  const run = (action: QuickAction) => { onClose(); action.run(); };
  return <Modal open={open} onClose={onClose} labelId="quick-actions-title" className="command-dialog"><h2 className="sr-only" id="quick-actions-title">Quick actions</h2><div className="command-search"><Icon name="search" /><input ref={input} role="combobox" aria-expanded={open} aria-controls="quick-action-list" aria-activedescendant={filtered[active] ? `quick-action-${filtered[active].id}` : undefined} autoComplete="off" aria-label="Search actions" placeholder="Where would you like to go?" value={query} onChange={(event) => { setQuery(event.target.value); setActive(0); }} onKeyDown={(event) => {
    if (["ArrowDown", "ArrowUp"].includes(event.key)) {
      event.preventDefault();
      setActive((current) => filtered.length ? (current + (event.key === "ArrowDown" ? 1 : -1) + filtered.length) % filtered.length : 0);
    }
    if (event.key === "Enter" && filtered[active]) { event.preventDefault(); run(filtered[active]); }
  }} /><button className="key-hint" onClick={onClose} aria-label="Close quick actions">Esc</button></div><div className="command-results"><span className="command-caption">{query ? "MATCHING ACTIONS" : "NAVIGATE YOUR WORKSPACE"}</span><div id="quick-action-list" role="listbox" aria-label="Workspace actions">{filtered.map((action, index) => <button key={action.id} id={`quick-action-${action.id}`} role="option" aria-selected={index === active} className={`command-action ${index === active ? "highlighted" : ""}`} onFocus={() => setActive(index)} onMouseEnter={() => setActive(index)} onClick={() => run(action)}><span className="command-icon"><Icon name={action.icon} /></span><span><strong>{action.title}</strong><small>{action.detail}</small></span><Icon name="arrow" size={16} /></button>)}</div>{!filtered.length && <div className="command-empty"><Icon name="search" /><strong>No matching actions</strong><p>Try “evidence”, “map”, or “settings”.</p></div>}</div><div className="command-footer"><span><kbd>↑</kbd><kbd>↓</kbd> to navigate</span><span><kbd>↵</kbd> to open</span></div></Modal>;
}
