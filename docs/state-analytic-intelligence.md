# SUGAR State Analytic Intelligence

This document describes SUGAR's advanced analytic layer for the Diplomacy Lab State Department project. It sits **after** collection, normalization, State-specific coding, and human verification. It is intended to make synthesis more rigorous, comparative, updateable, and useful at both the micro-case and macro-network level.

It is not an official Department of State or Intelligence Community analytic system, certification, or substitute for analyst judgment. Its tradecraft is deliberately designed around several principles reflected in ICD 203 analytic standards: source quality, explicit uncertainty, distinction between assumptions and judgments, consideration of alternatives and contrary information, relevance, and indicators/signposts. State public-diplomacy guidance also emphasizes themes, audiences, goals, results, significant developments, and lessons that can inform other missions.

References:
- ODNI, ICD 203, *Analytic Standards*: https://www.dni.gov/files/documents/ICD/ICD-203.pdf
- Department of State, 10 FAH-1 H-040, *Public Diplomacy Strategic Planning, Reporting and Evaluations*: https://fam.state.gov/FAM/10FAH01/10FAH010040.html
- Department of State, 10 FAH-1 H-060, *Social Media and Digital Engagement*: https://fam.state.gov/FAM/10FAH01/10FAH010060.html

## Why this layer exists

A large OSINT dataset does not automatically produce useful analysis. Raw counts can be misleading because:

- countries can have different source/platform coverage;
- a new query or collector can create apparent growth;
- social engagement is not equivalent to persuasion;
- a recurring actor is not automatically a coordinator;
- two similar programs are not automatically centrally directed;
- a high-volume country is not necessarily more strategically important than a lower-volume country;
- a missing observation can reflect a collection gap rather than absence of activity;
- a confident model can still be reasoning from weak or unrepresentative evidence.

The analytic-intelligence layer therefore has two stages:

1. **Deterministic analytic substrate** — measures the structure of the corpus before an LLM sees it.
2. **Evidence-constrained agentic synthesis** — multiple specialist agents interpret that substrate, challenge each other, and produce a revised synthesis without changing human-verification states.

The central pipeline is:

**Verified evidence -> deterministic macro/micro intelligence packet -> parallel specialist agents -> draft integration -> red team -> revised integration -> competing-hypothesis matrix -> longitudinal comparison**

## 1. Deterministic intelligence packet

Use:

```bash
sugar-intel packet observations.xlsx state.reviewed.jsonl \
  --output intelligence.json
```

Country scope:

```bash
sugar-intel packet observations.xlsx state.reviewed.jsonl \
  --country example host country \
  --output example host country.intelligence.json
```

Micro-case scope:

```bash
sugar-intel packet observations.xlsx state.reviewed.jsonl \
  --observation-id obs_... \
  --output case.intelligence.json
```

The packet is deterministic: rerunning it against the same evidence should produce the same substantive structure apart from generation time.

### Macro structure

The packet reports distributions for:

- countries and cities;
- observation types;
- program domains;
- strategic audiences;
- narratives;
- delivery modes;
- sponsor-support levels;
- source types.

It also calculates normalized entropy and Herfindahl-Hirschman concentration (HHI) for audiences, program domains, and narratives.

These are **portfolio-structure measures**, not influence measures.

A high audience HHI means the observed verified portfolio is concentrated in a smaller set of audiences. A low HHI means it is distributed more broadly. Neither means the activity was effective.

### Institutionalization and local embedding indicators

The packet reports descriptive shares such as:

- institution/program/partnership observations among verified records;
- records involving host or partner entities;
- verified records with material U.S. public-diplomacy overlap.

These help distinguish an observed portfolio dominated by isolated posts/events from one that appears repeatedly embedded in institutions or partnerships.

They do **not** prove strategic intent, control, or durability by themselves.

### Corpus comparability

Cross-country comparison is one of the easiest ways to produce false precision.

SUGAR therefore estimates **research-corpus comparability**, combining:

- similarity in source-type mix;
- overlap in temporal coverage;
- similarity in verification rates.

The result is labeled weak, moderate, or strong.

A strong score means the two country corpora are more suitable for descriptive comparison. It does not mean the countries themselves are similar.

If Country A is collected mainly from official institutional sources over twelve months while Country B is represented mainly by one social platform over six weeks, SUGAR should warn against simply comparing counts.

### Temporal structure

The packet builds month-level series for:

- total observations;
- verified observations;
- country breadth;
- city breadth;
- actor breadth;
- domain breadth;
- audience breadth;
- narrative breadth.

It can flag low-confidence candidates such as:

- observed activity acceleration;
- geographic broadening;
- program diversification;
- recurrent actor embedding.

These are intentionally labeled **collection-sensitive**. Analysts should first ask whether the query plan, source access, language coverage, or verification pace changed.

### Recurrent and cross-border actors

SUGAR counts recurring sponsors, hosts, partners, and actors and records:

- observation recurrence;
- country breadth;
- city breadth;
- associated domains;
- associated audiences;
- associated narratives.

An actor recurring across several countries is analytically interesting because it may identify an organizational bridge or reusable program mechanism.

It is **not automatically evidence of coordination or central direction**.

### Digital/offline coupling candidates

SUGAR looks for digital posts and offline program/event/institution observations that:

- occur in the same country;
- share actors, sponsors, hosts, partners, institutions, or programs;
- occur within a bounded period when dates are available.

This can identify cases where digital activity appears connected to real-world programming.

The output is a **coupling candidate**, not proof that the digital activity caused attendance, persuasion, or program outcomes.

### Descriptive archetype clusters

Verified observations are represented as feature sets containing domains, audiences, narratives, actors, sponsors, hosts, partners, institutions, and programs.

SUGAR uses feature similarity to identify recurring descriptive archetypes.

An archetype may reveal, for example, repeated observations combining:

- university host institutions;
- STEM/technology programming;
- student audiences;
- technology/innovation narratives.

The cluster is useful because an analyst can investigate whether the pattern reflects a reusable model, shared sponsor, common local incentives, or merely similar programming choices.

The cluster itself does not establish common direction.

### Robust reach/engagement anomalies

Within-country reach and engagement metrics can be compared using a robust median/MAD outlier rule.

This identifies unusually high observed attendance, views, likes, comments, or shares **relative to other records in that country corpus**.

An outlier is a prioritization signal. It is not an influence finding.

### Case comparables

Every case profile receives similar cases based on shared evidence-coded features.

This supports a micro-level question that normal reporting often misses:

> Is this observation actually unusual, or is it one instance of a recurring pattern?

The case dossier also exposes:

- evidence diversity;
- unresolved location issues;
- support uncertainty;
- U.S. overlap;
- high-consequence claims;
- source identities;
- comparable cases.

## 2. Agentic synthesis

Run:

```bash
export SUGAR_LLM_API_KEY='...'

sugar-intel synthesize observations.xlsx state.reviewed.jsonl \
  --provider arc \
  --model <approved-model> \
  --depth standard \
  --output ./analysis
```

The output includes:

- structured synthesis JSON;
- briefing-oriented Markdown;
- one JSONL row per specialist/red-team agent;
- a run manifest.

### Quick mode

`--depth quick`

Use for inexpensive exploratory analysis.

It runs a small number of agents and one integration pass. It does not run the full red-team/revision cycle.

Quick-mode judgments should generally be treated as provisional.

### Standard mode

`--depth standard`

Standard mode is the default.

For global synthesis it uses specialist roles including:

- system-pattern analyst;
- network/mechanism analyst;
- comparative analyst;
- public-diplomacy analyst;
- trajectory/indicators analyst;
- methodologist.

The specialists run in parallel. Their outputs are then integrated into a draft. A separate red-team pass challenges the draft. A final integration pass revises the synthesis in light of the critique.

### Deep mode

`--depth deep`

Deep mode adds hierarchical country analysis beneath the global synthesis.

The leading countries in the verified corpus receive dedicated country agents. Their findings are then available to the global integration layer alongside the cross-country specialist agents.

Deep mode is appropriate for major sponsor updates, periodic analytical reviews, or when the corpus has enough country depth to justify hierarchical analysis.

It is not automatically better when the underlying data are thin.

## 3. Agent roles

### System-pattern analyst

Looks for:

- recurring program models;
- portfolio structure;
- unusual configurations;
- structural changes;
- patterns that persist across cases.

### Network/mechanism analyst

Looks at:

- recurring actors;
- sponsors/hosts/partners;
- cross-border recurrence;
- network bridges;
- archetypes;
- digital/offline coupling.

This agent must propose multiple plausible mechanisms rather than treating recurrence as coordination.

### Comparative analyst

Uses the corpus-comparability diagnostics to decide when country comparison is defensible.

It should explicitly identify cases where a comparison is **not** analytically safe.

### Public-diplomacy analyst

Examines:

- audience overlap with American Spaces/EducationUSA;
- program-domain overlap;
- geographic overlap;
- potential competition/complementarity;
- what a post or bureau would need to understand.

It must not infer displacement, persuasion, or competitive success from overlap alone.

### Methodologist

Acts as a standing skeptic.

It attacks:

- source concentration;
- collection gaps;
- query bias;
- platform bias;
- temporal asymmetry;
- different verification rates;
- weak corroboration;
- engagement/influence conflation;
- spurious trend claims.

### Trajectory/indicators analyst

Takes candidate trends seriously but conditionally.

It develops observable indicators that would:

- strengthen the trajectory assessment;
- weaken it;
- falsify it;
- distinguish a real-world pattern from a collection artifact.

### Country analyst

Deep mode can create dedicated country analysts that integrate:

- footprint;
- institutional actors;
- program portfolio;
- audiences;
- narratives;
- U.S. overlap;
- unusual cases;
- alternatives;
- priority gaps.

### Case analyst

Micro mode focuses on a single observation and asks:

- What is directly observed?
- What is inferred?
- What is the evidence chain?
- Is sponsor support actually established?
- What mechanism could explain the observation?
- What comparable cases exist?
- What evidence cuts against the leading explanation?
- What would change the assessment?

## 4. Evidence constraints

Agentic analysis is allowed to reason aggressively, but it is not allowed to fabricate its evidentiary base.

SUGAR provides an evidence allowlist derived from the case packet.

If an agent invents a URL, observation ID, assessment ID, claim ID, or other evidence reference, the reference is discarded.

If a substantive judgment is left with no valid supporting reference, SUGAR changes it to:

- status: `hypothesis`;
- confidence: `low`.

This does not prove that a cited judgment is correct. It prevents unsupported prose from masquerading as a sourced assessment.

## 5. Probability and confidence

SUGAR intentionally treats **likelihood** and **analytic confidence** as separate concepts.

Allowed likelihood language is:

- very unlikely;
- unlikely;
- roughly even chance;
- likely;
- very likely;
- almost certain;
- not estimative.

Confidence is:

- low;
- moderate;
- high.

Example:

> It is **likely** that the observed programming model will recur in the next reporting period, but confidence is **low** because the corpus contains only a small number of recent cases and collection coverage changed.

Likelihood is the assessment about the proposition. Confidence is how much weight the analyst should place on that assessment given the evidence and method.

## 6. Assumptions, contrary evidence, and indicators

Every key judgment can contain:

- supporting evidence refs;
- contrary refs;
- assumptions;
- basis;
- indicators/signposts;
- implication;
- likelihood;
- confidence.

A strong synthesis should explain what could make the judgment wrong.

Indicators are especially important for an updateable research system. A useful judgment should generate future observable questions such as:

- Does the same sponsor appear in additional countries?
- Do host institutions begin repeating the same program package?
- Does activity persist after a one-off flagship event?
- Does apparent expansion remain after collection coverage is normalized?
- Does digital engagement connect to identifiable offline participation or outcomes?
- Does explicit U.S.-comparative messaging increase, decrease, or disappear?

## 7. Red team

Standard and deep modes include a separate red-team pass.

The red team receives the draft and attacks:

- unsupported causal language;
- confirmation bias;
- missing alternatives;
- engagement/influence conflation;
- weak source quality;
- unsafe comparisons;
- hidden collection effects;
- confidence that exceeds the evidence.

The final integrator receives both the original specialist outputs and the red-team critique.

The final product should preserve meaningful disagreement rather than forcing artificial consensus.

## 8. Competing hypotheses

After synthesis:

```bash
sugar-intel hypotheses ./analysis/analytic_intelligence.synthesis.json \
  --output ./analysis
```

This produces:

- hypothesis JSON;
- a flat hypothesis CSV;
- a Markdown matrix summary.

The matrix tracks which evidence:

- supports a hypothesis;
- contradicts a hypothesis;
- is neutral/unassessed;
- discriminates between hypotheses.

It also provides a **least-inconsistent ordering**.

This is not a probability estimate.

A hypothesis with few contradictions can still be weak if the relevant evidence was never collected.

Analysts should prioritize **discriminating collection** over simply accumulating additional supportive examples.

## 9. Longitudinal intelligence

Compare synthesis runs:

```bash
sugar-intel compare august.synthesis.json september.synthesis.json \
  --kind synthesis \
  --output september_change.json
```

Compare deterministic packets:

```bash
sugar-intel compare august.packet.json september.packet.json \
  --kind packet \
  --output september_corpus_change.json
```

Judgment comparison tracks:

- new judgments;
- removed judgments;
- changed likelihood;
- changed confidence;
- added supporting evidence;
- removed supporting evidence;
- new contrary evidence.

Packet comparison tracks changes in:

- record counts;
- verification volume;
- country shares;
- domain shares;
- audience shares;
- narrative shares;
- source mix;
- observed temporal signals.

The system explicitly warns that a changed assessment can reflect:

- new real-world evidence;
- new collectors or sources;
- changed queries;
- access restrictions;
- verification throughput;
- model variation;
- changed analyst framing.

Evidence-reference deltas should therefore be reviewed before interpreting an assessment change as a real-world change.

## 10. What sophisticated analysis should look like

A useful macro judgment is not:

> Country A had 70 posts and Country B had 30, therefore Country A has more sponsoring-state influence.

A useful judgment is closer to:

> The verified corpus shows a recurring student/STEM programming archetype across several locations, with repeated host partnerships and a small number of cross-border actors. The pattern is analytically notable, but confidence that it reflects centrally coordinated expansion should remain limited until collection establishes common sponsorship, planning, or funding. Cross-country volume comparison is unsafe where source and temporal coverage diverge.

A useful micro judgment is not:

> This event received 10,000 views, therefore it was influential.

A useful judgment is closer to:

> This event is a reach outlier relative to other verified cases in the same country corpus and resembles several student/STEM observations sharing the same host network. The available evidence supports treating it as a high-priority case for outcome collection, but views alone do not establish persuasion, attendance, or durable audience effects.

## 11. Human analyst responsibilities

Agentic synthesis does **not** alter human-verification states in `ResearchObservation` or `StateAssessment`.

A human analyst remains responsible for:

- verifying high-consequence facts and relationships;
- adjudicating support claims;
- deciding whether a contradiction is substantive;
- checking original-language/context issues;
- reconciling collection changes;
- validating policy relevance;
- deciding what enters a sponsor-facing product.

The purpose of the agentic layer is to make the analyst harder to surprise: surface structure, generate alternatives, connect micro cases to macro patterns, expose uncertainty, and propose discriminating next questions.
