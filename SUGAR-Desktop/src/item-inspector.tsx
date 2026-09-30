import { useEffect, useState, type ReactElement } from "react";
import { research } from "./research-api";
import type { ResultItem } from "./research-types";
import { Pill, Spinner, formatTime, languageName, platformLabel, titleCase } from "./ui";

const CHAIN_LABELS: Record<string, string> = {
  search_result: "Search result", fetched_document: "Fetched document", extracted_paragraph: "Extracted paragraph",
  translated_paragraph: "Translated paragraph", coded_finding: "Coded finding",
};

/** Slide-over showing one item's full text, translation, provenance, transformations and evidence chain. */
export function ItemInspector({ projectId, runId, itemId, author, onClose }: { projectId: string; runId: string; itemId: string; author: string; onClose: () => void }) {
  const [item, setItem] = useState<ResultItem | null>(null);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => {
    let active = true;
    setItem(null); setError("");
    research.item(projectId, runId, itemId).then((value) => { if (active) setItem(value); }).catch((issue) => { if (active) setError(issue instanceof Error ? issue.message : String(issue)); });
    return () => { active = false; };
  }, [projectId, runId, itemId]);

  const addNote = async () => {
    if (!note.trim()) return;
    await research.addNote(projectId, note.trim(), author, itemId, runId);
    setNote(""); setSaved(true);
    setItem(await research.item(projectId, runId, itemId));
    setTimeout(() => setSaved(false), 1500);
  };

  const chain = item?.evidence_chain || [];
  const byParent = (parent: string) => chain.filter((node) => node.parent === parent);
  const roots = chain.filter((node) => !node.parent || !chain.some((other) => other.id === node.parent));
  const renderNode = (node: (typeof chain)[number], depth: number): ReactElement => (
    <li key={node.id} style={{ marginLeft: `${depth * 0.9}rem` }}>
      <span className={`chain-dot chain-${node.type}`} aria-hidden="true" />
      <div><strong>{CHAIN_LABELS[node.type] || titleCase(node.type)}</strong>
        <small>{node.type === "search_result" ? `query “${node.data.query}” on ${node.data.platform}` : node.type === "fetched_document" ? `${node.data.chars} characters retrieved ${formatTime(node.data.retrieved_at)}` :
          node.type === "extracted_paragraph" ? `paragraph ${Number(node.data.index) + 1}` : node.type === "translated_paragraph" ? `${node.data.provider} · ${node.data.model} → ${node.data.target_language}` : String(node.data.label || "")}</small></div>
      {byParent(node.id).length > 0 && <ul>{byParent(node.id).map((child) => renderNode(child, depth + 1))}</ul>}
    </li>);

  return (
    <div className="inspector-backdrop" onClick={onClose}>
      <aside className="evidence-inspector item-inspector" role="dialog" aria-modal="true" aria-label="Item details" onClick={(event) => event.stopPropagation()}>
        <div className="inspector-top"><div><span className="eyebrow">COLLECTED ITEM</span><button className="inspector-close" onClick={onClose} aria-label="Close details">×</button></div>
          {item ? <div className="inspector-identity"><div><h2>{platformLabel(item.platform)} · {item.author || "unknown author"}</h2><span>{item.published_at ? new Date(item.published_at).toLocaleString() : "date not recorded"}</span></div></div> : <div className="inspector-identity"><Spinner /></div>}
          {item && <div className="inspector-badges"><Pill tone={item.status === "processed" || item.status === "collected" ? "ok" : "warn"}>{titleCase(item.status)}</Pill><Pill>{languageName(item.language || "und")}</Pill>
            {item.duplicate_of && <Pill tone="warn">Duplicate of an earlier item</Pill>}{!item.is_new && <Pill tone="info">Seen in an earlier run</Pill>}</div>}
        </div>
        <div className="inspector-content">
          {error && <div className="inline-error">{error}</div>}
          {item && <>
            <div className="inspector-section"><span className="eyebrow">ORIGINAL</span><p className="item-text" dir="auto">{item.original_text}</p>
              {item.url && <a className="source-link" href={item.url} target="_blank" rel="noreferrer"><span className="source-icon">↗</span><span><strong>Open the original</strong><small>{item.url}</small></span></a>}</div>
            {item.translated_text && <div className="inspector-section"><span className="eyebrow">TRANSLATION</span><p className="item-text" dir="auto">{item.translated_text}</p>
              <small className="muted">{item.translation_provider} · {item.translation_model} · {formatTime(item.translation_at, true)} · run {item.run_id}</small></div>}
            {!item.translated_text && item.translation_status && <div className="notice notice-warn">Translation {item.translation_status}{item.translation?.reason ? ` (${String(item.translation.reason).replaceAll("_", " ")})` : ""}.</div>}
            <div className="inspector-section"><span className="eyebrow">PROVENANCE</span>
              <dl className="kv">
                <div><dt>Platform</dt><dd>{platformLabel(item.platform)}</dd></div>
                <div><dt>Original URL / id</dt><dd>{item.url || item.native_id}</dd></div>
                <div><dt>Retrieved</dt><dd>{item.retrieved_at}</dd></div>
                <div><dt>Discovered by query</dt><dd><code>{item.query}</code>{item.query_dispatched && item.query_dispatched !== item.query ? <> sent as <code>{item.query_dispatched}</code></> : null}</dd></div>
                {item.queries.length > 1 && <div><dt>Also found by</dt><dd>{item.queries.slice(1).join(", ")}</dd></div>}
                <div><dt>Language</dt><dd>{languageName(item.language || "und")} ({item.language_method || "n/a"})</dd></div>
                <div><dt>Project</dt><dd>{item.project_id}</dd></div>
                <div><dt>Run</dt><dd>{item.run_id}{item.derived_from?.run_id ? ` · reprocessed from ${item.derived_from.run_id}` : ""}</dd></div>
                <div><dt>Collection status</dt><dd>{titleCase(item.status)}{item.rejection_reason ? ` — ${item.rejection_reason}` : ""}</dd></div>
                {item.geography.length > 0 && <div><dt>Geography</dt><dd>{item.geography.join(", ")}</dd></div>}
              </dl></div>
            <div className="inspector-section"><span className="eyebrow">EVIDENCE CHAIN</span>
              <ul className="chain">{roots.map((node) => renderNode(node, 0))}</ul>
              <small className="muted">Each step links back to the one before it, so a finding can be traced to the original post.</small></div>
            <div className="inspector-section"><span className="eyebrow">TRANSFORMATIONS</span>
              <ol className="transform-list">{(item.transformations || []).map((step, index) => (
                <li key={index}><strong>{titleCase(String(step.step))}</strong><small>{formatTime(String(step.at || ""), true)}{Object.entries(step).filter(([k]) => !["step", "at"].includes(k)).map(([k, v]) => ` · ${k}: ${typeof v === "object" ? JSON.stringify(v) : String(v)}`).join("")}</small></li>))}</ol></div>
            <div className="inspector-section"><span className="eyebrow">NOTES</span>
              {(item.notes || []).map((n) => <p className="note-line" key={String(n.note_id)}><strong>{String(n.author)}</strong> {String(n.text)}</p>)}
              <div className="note-add"><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add a note about this item" onKeyDown={(event) => { if (event.key === "Enter") void addNote(); }} aria-label="Note" />
                <button className="button button-secondary button-small" disabled={!note.trim()} onClick={() => void addNote()}>{saved ? "Saved ✓" : "Add"}</button></div></div>
          </>}
        </div>
      </aside>
    </div>
  );
}
