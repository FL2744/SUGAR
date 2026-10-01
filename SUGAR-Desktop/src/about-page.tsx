import { EmptyState } from "./ui";

export const CONTRIBUTORS = ["Alejandro Grenier", "William Taggart"];

export function AboutPage({ version, engineVersion }: { version: string; engineVersion: string }) {
  return (
    <section className="page-content about-page">
      <div className="page-heading compact-heading"><div><div className="eyebrow">ABOUT <span className="eyebrow-line" /></div><h1>SUGAR</h1>
        <p>System for User-Generated Content Gathering, Analysis, and Representation</p></div></div>
      <div className="panel about-card">
        <h3>Research orchestration, collection, translation, and evidence management</h3>
        <p>SUGAR turns a plain-language research request into an inspectable, executable, and reproducible collection workflow, and keeps every source, translation, and transformation traceable.</p>
        <dl className="kv"><div><dt>Desktop version</dt><dd>{version}</dd></div><div><dt>Research engine</dt><dd>{engineVersion || "not connected"}</dd></div><div><dt>License</dt><dd>Apache License 2.0</dd></div></dl>
        <h3>Authors</h3>
        <ul className="credit-list">{CONTRIBUTORS.map((name) => <li key={name}><strong>{name}</strong></li>)}</ul>
        <h3>Developed for</h3>
        <p>Virginia Tech Diplomacy Lab research and classroom workflows.</p>
        <p className="muted">Copyright 2026 Alejandro Grenier, William Taggart, and contributors. Third-party components and their licenses are listed in THIRD_PARTY_NOTICES.md.</p>
      </div>
      <EmptyState icon="☷" title="Where to learn more">See the README and the docs/ folder in the repository for the research workbench, activity events, provider setup, and export formats.</EmptyState>
    </section>
  );
}
