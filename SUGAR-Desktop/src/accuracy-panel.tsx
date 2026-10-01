import { useState } from "react";
import { research } from "./research-api";
import type { AccuracyReport, Prf } from "./research-types";
import { Spinner, titleCase } from "./ui";

const fmt = (v: number | null) => (v === null ? "—" : `${Math.round(v * 100)}%`);
const Row = ({ label, m }: { label: string; m: Prf }) => <tr><td>{label}</td><td>{fmt(m.precision)}</td><td>{fmt(m.recall)}</td><td>{fmt(m.f1)}</td><td>{m.tp} / {m.fp} / {m.fn}</td></tr>;

/** Measure how closely SUGAR's suggestions match a person's labels on a random sample. */
export function AccuracyPanel({ projectId, runId, onClose, onError }: { projectId: string; runId: string; onClose: () => void; onError: (m: string) => void }) {
  const [busy, setBusy] = useState("");
  const [report, setReport] = useState<AccuracyReport | null>(null);
  const download = async () => {
    setBusy("sample");
    try {
      const csv = await research.accuracySample(projectId, runId, 60);
      const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" })); link.download = `labeling-sheet-${runId}.csv`; link.click(); URL.revokeObjectURL(link.href);
    } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };
  const score = async (file: File | undefined) => {
    if (!file) return;
    setBusy("score");
    try { setReport(await research.accuracyScore(projectId, runId, await file.text())); } catch (e) { onError(e instanceof Error ? e.message : String(e)); } finally { setBusy(""); }
  };
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section className="modal candidates-panel" role="dialog" aria-modal="true" aria-labelledby="acc-title" onClick={(event) => event.stopPropagation()}>
        <header className="modal-head"><div><span className="eyebrow">ACCURACY CHECK</span><h2 id="acc-title">How well do the suggestions match your judgment?</h2></div><button className="text-button" onClick={onClose}>Close</button></header>
        <div className="modal-body">
          <ol className="steps"><li><strong>Get a labeling sheet.</strong> A random sample of 60 items, with no suggestions shown so they cannot influence you.</li>
            <li><strong>Fill it in.</strong> In <code>gold_relevance</code> write relevant or not_relevant. Optionally list audiences and programs separated by semicolons, using the standard labels (for example <code>university_students</code>).</li>
            <li><strong>Upload it.</strong> SUGAR reports precision, recall and F1 for relevance, audiences and programs.</li></ol>
          <div className="preview-actions"><button className="button button-secondary" onClick={() => void download()} disabled={Boolean(busy)}>{busy === "sample" ? <Spinner /> : "Download labeling sheet"}</button>
            <label className="button button-primary file-button">{busy === "score" ? <Spinner /> : "Upload filled sheet…"}<input type="file" accept=".csv,text/csv" className="sr-only" aria-label="Filled labeling sheet" onChange={(e) => { void score(e.currentTarget.files?.[0]); e.currentTarget.value = ""; }} /></label></div>
          {report && <>
            <p role="status">Compared {report.labeled_relevance} relevance labels and {report.labeled_coding} coded items{report.unknown_item_ids ? `; ${report.unknown_item_ids} rows did not match an item in this run` : ""}.</p>
            <table className="accuracy-table"><thead><tr><th>Measure</th><th>Precision</th><th>Recall</th><th>F1</th><th>Right / extra / missed</th></tr></thead><tbody>
              <Row label={`Relevance (score ≥ ${report.relevance.threshold})`} m={report.relevance} />
              <Row label="Audiences (all)" m={report.audience.overall} /><Row label="Programs (all)" m={report.program.overall} />
              {Object.entries(report.audience.by_label).map(([k, m]) => <Row key={`a${k}`} label={`Audience: ${titleCase(k)}`} m={m} />)}
              {Object.entries(report.program.by_label).map(([k, m]) => <Row key={`p${k}`} label={`Program: ${titleCase(k)}`} m={m} />)}</tbody></table>
            <details><summary>Relevance at other cut-offs</summary><table className="accuracy-table"><thead><tr><th>Score ≥</th><th>Precision</th><th>Recall</th><th>F1</th><th>Right / extra / missed</th></tr></thead><tbody>
              {Object.entries(report.relevance.by_threshold).map(([t, m]) => <Row key={t} label={t} m={m} />)}</tbody></table></details>
            <p className="footnote">{report.note}</p></>}
        </div>
      </section>
    </div>
  );
}
