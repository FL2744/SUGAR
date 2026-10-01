import { useEffect, useState, type ReactElement } from "react";
import { research } from "./research-api";
import type { CodeRow, Institution, ResultItem, ReviewState, Verdict } from "./research-types";
import { Pill, Spinner, VERDICTS, formatTime, languageName, platformLabel, titleCase } from "./ui";

const CHAIN_LABELS: Record<string, string> = {
  search_result: "Search result", fetched_document: "Fetched document", extracted_paragraph: "Extracted paragraph",
  translated_paragraph: "Translated paragraph", coded_finding: "Coded finding",
};

/** Slide-over showing one item's full text, translation, provenance, transformations and evidence chain. */
export function ItemInspector({ projectId, runId, itemId, author, onClose }: { projectId: string; runId: string; itemId: string; author: string; onClose: () => void }) {
  const [item, setItem] = useState<ResultItem | null>(null);
  const [error, setError] = useState("");
  const [review, setReview] = useState<ReviewState | null>(null);
  const [comment, setComment] = useState("");
  const [tag, setTag] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [linkTo, setLinkTo] = useState("");
  const [newName, setNewName] = useState("");
  const [quote, setQuote] = useState("");
  const [linkMsg, setLinkMsg] = useState("");
  const [codes, setCodes] = useState<CodeRow[]>([]);
  const [applyTo, setApplyTo] = useState("");
  const [codeMsg, setCodeMsg] = useState("");
  useEffect(() => {
    let active = true;
    setItem(null); setError(""); setReview(null); setReviewError("");
    research.item(projectId, runId, itemId).then((value) => { if (active) { setItem(value); setReview((value as unknown as { review?: ReviewState }).review || null); } }).catch((issue) => { if (active) setError(issue instanceof Error ? issue.message : String(issue)); });
    return () => { active = false; };
  }, [projectId, runId, itemId]);

  useEffect(() => { void research.institutions(projectId).then((r) => setInstitutions(r.institutions)).catch(() => undefined); }, [projectId]);
  useEffect(() => { void research.coding(projectId, itemId).then(setCodes).catch(() => undefined); }, [projectId, itemId]);
  const decideCode = async (code: CodeRow, decision: "confirm" | "reject") => {
    setCodeMsg("");
    try { setCodes(await research.decideCode(projectId, itemId, runId, code.field, code.label, decision, "", author)); }
    catch (issue) { setCodeMsg(issue instanceof Error ? issue.message : String(issue)); }
  };
  const applyCodes = async () => {
    try { const r = await research.applyCodes(projectId, runId, itemId, applyTo, author); setCodeMsg(`Added ${r.applied.length} confirmed label${r.applied.length === 1 ? "" : "s"} to the institution, each citing this item.`); }
    catch (issue) { setCodeMsg(issue instanceof Error ? issue.message : String(issue)); }
  };
  const link = async () => {
    setLinkMsg("");
    try {
      const existing = institutions.find((i) => i.entity_id === linkTo);
      const saved = await research.recordInstitution(projectId, { values: { name: existing ? existing.name : newName.trim() }, entity_id: existing?.entity_id,
        evidence: [{ run_id: runId, item_id: itemId, quote: quote.trim() }], author });
      setLinkMsg(`Linked to ${saved.name}.`); setQuote(""); setNewName("");
      setInstitutions((await research.institutions(projectId)).institutions);
    } catch (issue) { setLinkMsg(issue instanceof Error ? issue.message : String(issue)); }
  };
  const act = async (action: Record<string, unknown>) => {
    setReviewError("");
    try { setReview((await research.postReview(projectId, itemId, action, author)).review); }
    catch (issue) { setReviewError(issue instanceof Error ? issue.message : String(issue)); }
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
            <div className="inspector-section review-section"><span className="eyebrow">TEAM REVIEW</span>
              <div className="verdict-row" role="group" aria-label="Verdict">
                {VERDICTS.map((v) => <button key={v.id} type="button" className={`button button-secondary button-small ${review?.verdict === v.id ? "on" : ""}`} aria-pressed={review?.verdict === v.id}
                  onClick={() => void act({ kind: "verdict", verdict: (review?.verdict === v.id ? "" : v.id) as Verdict })}><span aria-hidden="true">{v.mark}</span> {v.label}</button>)}
              </div>
              {review?.verdict && <small className="muted">Marked {VERDICTS.find((v) => v.id === review.verdict)?.label.toLowerCase()} by {review.verdict_by || "a team member"}{review.verdict_at ? ` · ${formatTime(review.verdict_at, true)}` : ""}</small>}
              <div className="tag-row" aria-label="Tags">
                {(review?.tags || []).map((t) => <span key={t} className="tag-chip">#{t}<button type="button" aria-label={`Remove tag ${t}`} onClick={() => void act({ kind: "tag_remove", tag: t })}>×</button></span>)}
                <input value={tag} onChange={(event) => setTag(event.target.value)} placeholder="Add a tag" aria-label="Add a tag" maxLength={40}
                  onKeyDown={(event) => { if (event.key === "Enter" && tag.trim()) { void act({ kind: "tag_add", tag }); setTag(""); } }} />
              </div>
              <ol className="comment-thread" aria-label="Comments">
                {(review?.comments || []).map((c) => <li key={c.id}><strong>{c.author}</strong> <small className="muted">{formatTime(c.at, true)}</small><p>{c.text}</p></li>)}
              </ol>
              <div className="note-add"><input value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Comment for your team" aria-label="Add a comment"
                onKeyDown={(event) => { if (event.key === "Enter" && comment.trim()) { void act({ kind: "comment", text: comment }); setComment(""); } }} />
                <button className="button button-secondary button-small" disabled={!comment.trim()} onClick={() => { void act({ kind: "comment", text: comment }); setComment(""); }}>Comment</button></div>
              {reviewError && <div className="inline-error" role="alert">{reviewError}</div>}
            </div>
            <div className="inspector-section"><span className="eyebrow">USE AS EVIDENCE FOR AN INSTITUTION</span>
              <div className="note-add">
                <select value={linkTo} onChange={(e) => setLinkTo(e.target.value)} aria-label="Institution">
                  <option value="">New institution…</option>{institutions.map((i) => <option key={i.entity_id} value={i.entity_id}>{i.name}{i.city ? ` · ${i.city}` : ""}</option>)}</select>
                {!linkTo && <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Institution name" aria-label="New institution name" />}
                <input value={quote} onChange={(e) => setQuote(e.target.value)} placeholder="Exact words from this item (optional)" aria-label="Quote from the item" />
                <button className="button button-secondary button-small" disabled={!linkTo && !newName.trim()} onClick={() => void link()}>Link</button></div>
              {linkMsg && <small className="muted" role="status">{linkMsg}</small>}
              <small className="muted">The quote must appear in this item. Verify the claims on the Institutions page.</small></div>
            {codes.length > 0 && <div className="inspector-section"><span className="eyebrow">WHAT THIS ITEM SUGGESTS (PROPOSED — CONFIRM OR REJECT)</span>
              <ul className="code-list">{codes.filter((c) => c.status !== "rejected").map((c) => (
                <li key={`${c.field}:${c.label}`} className={c.status}>
                  <div><strong>{c.field === "attendance" ? `Reported attendance: ${Number(c.label).toLocaleString()}` : `${titleCase(c.field.replace("_", " "))}: ${titleCase(c.label)}`}</strong>
                    {c.status === "confirmed" ? <Pill tone="ok">Confirmed{c.decided_by ? ` by ${c.decided_by}` : ""}</Pill> : <Pill>Proposed · {c.methods.join(" + ") || "pattern"}</Pill>}
                    {c.quote && <q dir="auto">{c.quote}</q>}</div>
                  {c.status !== "confirmed" && <div className="claim-actions"><button className="button button-secondary button-small" onClick={() => void decideCode(c, "confirm")}>✓ Confirm</button><button className="button button-quiet button-small" onClick={() => void decideCode(c, "reject")}>✕ Reject</button></div>}
                </li>))}</ul>
              {codes.some((c) => c.status === "confirmed" && (c.field === "audience" || c.field === "program")) && <div className="note-add">
                <select value={applyTo} onChange={(e) => setApplyTo(e.target.value)} aria-label="Institution to add the confirmed labels to"><option value="">Add confirmed labels to an institution…</option>{institutions.map((i) => <option key={i.entity_id} value={i.entity_id}>{i.name}</option>)}</select>
                <button className="button button-secondary button-small" disabled={!applyTo} onClick={() => void applyCodes()}>Add</button></div>}
              {codeMsg && <small className="muted" role="status">{codeMsg}</small>}
              <small className="muted">Proposals come from the item's own words. Attendance is as reported by the source, not verified.</small></div>}
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
            <div className="inspector-section"><span className="eyebrow">NOTES (EARLIER)</span>
              {(item.notes || []).map((n) => <p className="note-line" key={String(n.note_id)}><strong>{String(n.author)}</strong> {String(n.text)}</p>)}</div>
          </>}
        </div>
      </aside>
    </div>
  );
}
