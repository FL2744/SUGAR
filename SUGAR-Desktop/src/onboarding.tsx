import { useEffect, useRef, useState } from "react";
import { research } from "./research-api";
import type { ConnectionReport, PlatformRow, ProviderType } from "./research-types";
import type { Prefs } from "./prefs";
import { ConnectionResult } from "./settings-page";
import { Pill, Spinner, platformLabel } from "./ui";

type Choice = "openai" | "arc" | "other" | "none";
const STEPS = ["Welcome", "AI model", "Sources", "Ready"] as const;

const CHOICES: Array<{ id: Choice; title: string; body: string }> = [
  { id: "openai", title: "OpenAI", body: "Use your OpenAI API key." },
  { id: "arc", title: "Virginia Tech ARC", body: "Use your ARC API key. Many models are available." },
  { id: "other", title: "Another provider", body: "Anthropic, a local model, or any OpenAI-compatible service. Finish this in Settings." },
  { id: "none", title: "No AI for now", body: "SUGAR still collects, de-duplicates and organizes. Non-English posts won't be translated." },
];

/**
 * First-run setup: your name, which AI to use (tested before it is saved), what sources need, and a first example.
 * Nothing is stored until a step is finished, and every step can be skipped and revisited in Settings.
 */
export function Onboarding({ prefs, onSavePrefs, onFinish, onOpenSettings, onTryExample }: {
  prefs: Prefs; onSavePrefs: (prefs: Prefs) => boolean; onFinish: () => void; onOpenSettings: () => void; onTryExample: (text: string) => void;
}) {
  const [step, setStep] = useState(0);
  const [name, setName] = useState(prefs.name);
  const [choice, setChoice] = useState<Choice>("openai");
  const [secret, setSecret] = useState("");
  const [model, setModel] = useState("");
  const [types, setTypes] = useState<ProviderType[]>([]);
  const [report, setReport] = useState<ConnectionReport | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [connected, setConnected] = useState("");
  const [platforms, setPlatforms] = useState<PlatformRow[]>([]);
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => { void research.providers().then((r) => setTypes(r.types)).catch(() => undefined); }, []);
  useEffect(() => { if (step === 2) void research.platforms().then(setPlatforms).catch(() => undefined); }, [step]);
  useEffect(() => { headingRef.current?.focus(); }, [step]);

  const type = types.find((t) => t.id === (choice === "openai" ? "openai" : "arc"));
  const profile = () => ({ name: choice === "openai" ? "OpenAI" : "Virginia Tech ARC", type: choice === "openai" ? "openai" : "arc", model: model.trim() || type?.default_model || "" });

  const test = async () => {
    setBusy("test"); setError(""); setReport(null);
    try {
      const result = await research.testDraftProvider(profile(), secret.trim());
      setReport(result);
    } catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };
  const saveProvider = async () => {
    setBusy("save"); setError("");
    try {
      const saved = await research.saveProvider(profile(), secret.trim(), true);
      setConnected(saved.profile.name);
      try { localStorage.setItem("sugar.providerChoice", saved.profile.id); } catch { /* storage may be unavailable */ }
      setSecret("");           // the key now lives in the credential store; do not keep it in the page
      setStep(2);
    } catch (issue) { setError(issue instanceof Error ? issue.message : String(issue)); } finally { setBusy(""); }
  };
  const finish = (example = "") => {
    onSavePrefs({ ...prefs, name: name.trim(), onboarded: true });
    if (example) onTryExample(example);
    onFinish();
  };

  const needsKey = choice === "openai" || choice === "arc";
  const canTest = needsKey && secret.trim().length > 7 && !((report?.available_models.length || 0) > 0 && !model.trim());
  const models = report?.available_models || [];

  return (
    <div className="modal-backdrop onboarding-backdrop">
      <section className="modal onboarding" role="dialog" aria-modal="true" aria-labelledby="onboarding-title">
        <header className="modal-head">
          <div><span className="eyebrow">SETUP · STEP {step + 1} OF {STEPS.length}</span><h2 id="onboarding-title" ref={headingRef} tabIndex={-1}>{["Welcome to SUGAR", "Choose your AI model", "What SUGAR can search", "You're ready"][step]}</h2></div>
          <button className="text-button" onClick={() => finish()} aria-label="Skip setup">Skip setup</button>
        </header>
        <ol className="stepper" aria-hidden="true">{STEPS.map((label, index) => <li key={label} className={index === step ? "now" : index < step ? "done" : ""}>{index < step ? "✓" : index + 1} {label}</li>)}</ol>

        <div className="modal-body">
          {step === 0 && <>
            <p>SUGAR turns a plain-language research question into searches across public sources, then keeps every result with where it came from.</p>
            <label className="field-block"><span>What should we call you? <small>Shown on your reviews and comments</small></span>
              <input value={name} maxLength={60} onChange={(event) => setName(event.target.value)} placeholder="e.g. Alex Rivera" autoFocus /></label>
            <p className="footnote">Setup takes about two minutes. You can skip any step and come back from Settings.</p>
          </>}

          {step === 1 && <>
            <p>An AI model helps SUGAR understand your question and translate other languages. Pick the one you want to use; you can change it for any request.</p>
            <div className="choice-grid" role="radiogroup" aria-label="AI model provider">
              {CHOICES.map((c) => (
                <button key={c.id} type="button" role="radio" aria-checked={choice === c.id} className={`choice-card ${choice === c.id ? "on" : ""}`} onClick={() => { setChoice(c.id); setReport(null); setError(""); }}>
                  <strong>{c.title}</strong><small>{c.body}</small></button>))}
            </div>
            {needsKey && <div className="form-stack">
              <label className="field-block"><span>{type?.credential_label || "API key"}</span>
                <input type="password" autoComplete="off" spellCheck={false} value={secret} onChange={(event) => { setSecret(event.target.value); setReport(null); }} placeholder={`Paste your ${(type?.credential_label || "API key").toLowerCase()}`} /></label>
              <label className="field-block"><span>Model {models.length ? <small>from your account</small> : <small>optional — you can pick after testing</small>}</span>
                {models.length ? <select value={model} onChange={(event) => { setModel(event.target.value); setReport({ ...report!, ok: false }); }}><option value="">Choose a model…</option>{models.map((m) => <option key={m} value={m}>{m}</option>)}</select>
                  : <input value={model} onChange={(event) => setModel(event.target.value)} placeholder={type?.default_model || "model name"} />}</label>
              <div className="preview-actions">
                <button type="button" className="button button-secondary" onClick={() => void test()} disabled={!canTest || Boolean(busy)}>{busy === "test" ? <><Spinner /> Testing…</> : "Test connection"}</button>
                {report?.ok && <button type="button" className="button button-primary" onClick={() => void saveProvider()} disabled={Boolean(busy)}>{busy === "save" ? <><Spinner /> Saving…</> : "Save and continue"}</button>}
              </div>
              {report && <ConnectionResult report={report} />}
              <p className="footnote">Your key is stored in your computer's credential store, not in the project or the page.</p>
            </div>}
            {choice === "other" && <div className="notice notice-info">Open <button type="button" className="text-button" onClick={() => { finish(); onOpenSettings(); }}>Settings → LLM providers</button> to add Anthropic, a local model, or another compatible service.</div>}
            {choice === "none" && <div className="notice notice-info">You can add a model any time. Until then SUGAR uses its built-in interpreter.</div>}
            {error && <div className="inline-error" role="alert">{error}</div>}
          </>}

          {step === 2 && <>
            {connected && <div className="notice notice-ok" role="status"><strong>{connected} is connected</strong> and set as your default.</div>}
            <p>These sources work out of the box. Others need an account; add those keys later in Settings.</p>
            <ul className="source-list">
              {platforms.filter((p) => p.keyword_search).map((p) => (
                <li key={p.id}><div><strong>{platformLabel(p.id)}</strong><small className="muted">{p.description}</small></div>
                  <Pill tone={p.state === "ready" ? "ok" : "neutral"}>{p.state === "ready" ? "Ready" : "Needs a key"}</Pill></li>))}
              {platforms.length === 0 && <li className="muted"><Spinner /> Checking sources…</li>}
            </ul>
          </>}

          {step === 3 && <>
            <p>{name.trim() ? `${name.trim()}, you're` : "You're"} all set. Describe a topic in your own words and SUGAR will show you the plan before anything runs.</p>
            <div className="choice-grid">
              {["Look into reading rooms and cultural centers run by foreign governments in Southeast Asia", "What are people saying about climate policy in Brazil on Bluesky since 2023?"].map((example) => (
                <button key={example} type="button" className="choice-card" onClick={() => finish(example)}><strong>Try an example</strong><small>{example}</small></button>))}
            </div>
          </>}
        </div>

        <footer className="modal-foot">
          <button className="button button-quiet" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>Back</button>
          {step === 0 && <button className="button button-primary" onClick={() => { onSavePrefs({ ...prefs, name: name.trim() }); setStep(1); }}>Continue</button>}
          {step === 1 && <button className="button button-secondary" onClick={() => setStep(2)}>{choice === "none" || choice === "other" ? "Continue" : "Skip for now"}</button>}
          {step === 2 && <button className="button button-primary" onClick={() => setStep(3)}>Continue</button>}
          {step === 3 && <button className="button button-primary" onClick={() => finish()}>Start researching</button>}
        </footer>
      </section>
    </div>
  );
}
