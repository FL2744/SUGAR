# State delivery product contract

The authoritative requirement list for the State/Diplomacy Lab delivery profile is machine-readable at [`../../product/requirements/state_product.v1.json`](../../product/requirements/state_product.v1.json). This document explains the product boundary and implementation order; it is not a second independent requirement list.

## Product boundary

SUGAR should be delivered as a **portable research-orchestration and evidence workbench**, not as an attempt to replace every Department collection, media-analysis, or AI system.

Public Department material already describes:

- **Northstar**, an AI-enabled digital/news/social-media analytics capability that searches and translates media, generates summaries, and supports analysis of the global information environment;
- **StateChat**, the Department's enterprise generative-AI chatbot; and
- an **Enterprise Data Catalog** intended to make Department data assets discoverable and accessible on OpenNet.

Public basis reviewed for this decision (2026-09-17): the Department's current AI page, the 2024 AI Inventory, INR's OSINT Strategy, 20 FAM 101.3, and 1 FAM 040. Their URLs and the specific propositions they support are retained in the machine-readable contract so the assumptions can be revisited later rather than becoming undocumented project lore.

Therefore SUGAR's durable value should be the layer that remains useful regardless of which collector, enterprise media platform, or approved model service a Department user has available:

```text
research requirement
        |
        v
inspectable search / collection plan
        |
   +----+---------------------------+
   |                                |
   v                                v
SUGAR collectors             external State/partner data
   |                                |
   +-------------> canonical evidence <-------------+
                         |
                         v
             provenance + human review
                         |
                         v
       analysis / maps / change detection / brief
                         |
          +--------------+---------------+
          v                              v
   portable evidence package       downstream systems
```

No direct Northstar, StateChat, OpenNet, or other internal Department API should be coded until an actual supported interface is provided. File interchange is the minimum integration surface because it remains useful even when no API is available.

The implemented boundary now keeps these layers separable in the workspace catalog. External imports register canonical machine-readable evidence separately from human-friendly views, import manifests, and rejected rows; later research steps therefore resolve evidence rather than accidentally consuming provenance metadata as records. A partner/Department export can enter a project and produce a portable handoff without invoking a SUGAR collector or any LLM.

LLM-assisted operations use the shared provider configuration boundary for OpenAI, Virginia Tech ARC, or a custom OpenAI-compatible endpoint. Core requirement, planning, import, project inspection, review, and handoff operations remain usable without an LLM. Provider/model/workflow identity is recorded on AI-derived artifacts, and provider failure produces explicit review-needed state rather than a fabricated factual finding. No StateChat or other undocumented Department API client exists in runtime code.

## Delivery profiles

SUGAR should distinguish two profiles rather than forcing one environment to satisfy incompatible needs.

### Classroom/development profile

- Virginia Tech ARC may be offered as a convenient LLM provider.
- Live public collectors may be exercised directly.
- Developer diagnostics and experimental workflows may be visible.

### State delivery profile

- no Virginia Tech service is required;
- OpenAI/custom/no-LLM operation are first-class paths;
- import/export and project portability are prominent;
- collector and model failures are explicit rather than fatal to project inspection;
- State-specific assumptions are configuration, not hidden code constants;
- first-run workflow starts from a research requirement, not a manually authored keyword list.

The two profiles must share one core implementation. A State profile is not a fork.

## Current capability status in SUGAR 1.3.0

The original integration-first sequence below is retained as historical design context. The current repository now supports the following product paths:

- external CSV/JSONL data enters through canonical import, with a saved requirement, approved strategy, bounded search plan, review, and portable handoff;
- research-intelligence operations recommend a next collection action, preserve hypothesis proposals as paused branches, track text-similarity candidates, build a provenance-bearing entity/event graph, and run verified-evidence sensitivity checks;
- analyst projects can merge while retaining contributor artifacts and assessment conflicts, and desktop analytic outputs can report hash-based freshness and rebuild order;
- local media preservation, timestamped evidence citations, sanitized saved-page import, local lexical search, and explicitly opted-in remote embedding search are available in the shared core and both desktop workflows;
- optional DuckDB/Parquet analysis and a fixed offline calibration suite are available.

Known product gaps remain: OCR/ASR/keyframes are supplied externally rather than generated; capture is an HTML import flow rather than a browser extension; embeddings require an explicitly selected compatible remote service; pipeline reports do not replay builds and cover registered desktop derivations; and the six-case calibration suite does not establish field accuracy. Direct Department APIs, cloud collaboration, fully automatic alias resolution, and universal confidence scoring are still outside the product boundary.

## Original initial engineering sequence (historical)

The numbered sequence below documents the early integration-first plan. Use the current capability and remaining-gap summary above when assessing the 1.3.0 product state.

### 1. External data ingestion

Implement an `ImportAdapter` boundary next to the existing collector registry. Support CSV and JSONL first. This immediately lets SUGAR operate on data exported from another tool without knowing or caring how that system collected it.

The importer must map external records into `PostRecord`/`ResearchObservation` while preserving source identifiers and recording importer provenance. Unknown fields should be retained in an extension/raw metadata field where practical rather than discarded.

### 2. Research requirement object

Create a versioned object containing at minimum:

- question;
- decision/use context (optional);
- geography;
- timeframe;
- target audience;
- languages;
- known entities/aliases;
- source constraints;
- collection depth/budget; and
- analyst exclusions or protected constraints.

Store this object in the project workspace so every query plan and later refresh has a stable parent requirement.

Before an interpreted requirement drives planning, compile it into a separate versioned research-strategy artifact. That artifact must distinguish exact source-span concepts from semantic interpretations and search hypotheses, expose missing dimensions and operational research dimensions, and retain the original question unchanged. Deterministic compilation must work without an LLM; optional AI semantic compilation may enrich the artifact but cannot promote unsupported hypotheses into analyst-stated facts.

A named analyst must be able to edit/include/exclude interpreted concepts, hypotheses, and research dimensions and approve the compiled strategy. Any later edit must return the strategy to draft. Once a strategy exists for a requirement, the strategy-aware planner must reject it until approved and must record the approved strategy identity/reviewer in the resulting plan.

### 3. Search planner with bounded adaptation

The planner should generate a portfolio of query branches rather than one query. Branches should carry rationale, parentage, discovered concepts, yield, novelty, duplicate rate, coverage contribution, and status.

LLMs may propose terms and interpret retrieved evidence, but deterministic policy should decide whether a branch is allowed to expand beyond configured semantic/graph-hop boundaries and should preserve an audit record of every pivot.

Both desktop clients expose the same branch-review controls. An analyst can refresh the current plan, edit a branch query or rationale, and mark a branch approved, paused, or excluded. Every edit and status transition is appended to the saved plan event history with actor/reason metadata; evidence-driven feedback can still retire or pause branches using measured relevance, novelty, duplication, source diversity, and coverage gain.

### 4. Portable evidence package

Define a stable export bundle containing:

- project/run manifest;
- research requirement;
- approved compiled research strategy when used;
- search-plan/audit history;
- source/normalized evidence;
- claim-to-evidence relationships;
- review state;
- collection failures and limitations;
- model/provider metadata for AI artifacts;
- brief and machine-readable analysis outputs; and
- schema/software versions.

This package is the key handoff artifact if direct Department-system integration is impossible.

### 5. Human review and AI provenance

AI-generated classifications, extraction, and analytic suggestions remain explicitly marked as AI-triaged until a named analyst reviews them. The review workbook covers the underlying ResearchObservation as well as State assessments, claims, sponsor-support judgments, and source conflicts when present. Human-verified or rejected decisions require a named reviewer and are applied through validated state transitions rather than by silently editing flags.

For reproducibility, AI-derived observations and assessments record the provider, model, and workflow/prompt version that produced the suggestion. Those fields survive storage, review, lineage generation, and portable handoff. State-facing briefing logic remains verified-only: an assessment cannot become briefing-eligible merely because an AI model assigned a high confidence value.

### 6. Public/authorized access and data minimization

Collectors must stop or defer at unsupported authentication, anti-bot, verification, CAPTCHA, and rate-limit boundaries rather than manufacture access or interpret denial as evidence of zero activity. Existing authorized sessions may be supplied where the collector explicitly supports them; SUGAR must not synthesize login state, rotate identities, or bypass access controls.

Secrets are runtime inputs, not research artifacts. Desktop clients pass credentials separately from operation configuration, workspace manifests do not store them, and bridge event output redacts active secret values if an upstream exception echoes them.

The default State workflow is ecosystem/audience oriented. Canonical source evidence may retain the public account identity needed for provenance, but post authors are not automatically promoted into analytic actors or person dossiers. Adaptive search remains bounded to the research requirement and evidence-linked discoveries.

External datasets retain source-provided handling, usage, license, and ownership caveats as structured import provenance. Those caveats survive deliberate dropping of unrelated unmapped source columns and conflicting caveats from duplicate rows are unioned rather than silently overwritten.

### 7. State delivery UX

Only after the first four are stable should the desktop workflow be reorganized around:

1. **New Research Requirement**
2. **Compile / Review Research Strategy**
3. **Review Search Plan**
4. **Import or Collect**
5. **Run / Monitor Coverage**
6. **AI Triage / Prepare Assessment Suggestions**
7. **Human Review of Evidence and Findings**
8. **Export Brief / Evidence Package**
9. **Save as Monitor / Compare with Prior Run**

Platform-specific credential setup should live behind source configuration rather than dominate the State-facing workflow.

## What not to build first

Until a sponsor provides a concrete requirement, do not spend the remaining project time on:

- cloning Northstar's broad media-search/summarization feature set;
- a bespoke StateChat connector with an invented API;
- additional platform scrapers merely to increase platform count when the collector team is already working that lane;
- a universal influence/sentiment score;
- a hidden fully autonomous agent loop;
- custom enterprise authentication or OpenNet assumptions;
- deployment logic tied to Virginia Tech ARC.

## Definition of a credible handoff

The repository is ready for a serious State handoff when a new user on a clean machine can install SUGAR, open or create a project, enter a research requirement, import an external dataset or use an available collector, inspect the generated search/collection logic, review evidence-backed findings and limitations, and export a portable evidence package without access to Virginia Tech systems or knowledge of the internal codebase.
