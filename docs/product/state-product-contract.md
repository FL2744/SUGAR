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

## Highest-value engineering sequence

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

### 3. Search planner with bounded adaptation

The planner should generate a portfolio of query branches rather than one query. Branches should carry rationale, parentage, discovered concepts, yield, novelty, duplicate rate, coverage contribution, and status.

LLMs may propose terms and interpret retrieved evidence, but deterministic policy should decide whether a branch is allowed to expand beyond configured semantic/graph-hop boundaries and should preserve an audit record of every pivot.

### 4. Portable evidence package

Define a stable export bundle containing:

- project/run manifest;
- research requirement;
- search-plan/audit history;
- source/normalized evidence;
- claim-to-evidence relationships;
- review state;
- collection failures and limitations;
- model/provider metadata for AI artifacts;
- brief and machine-readable analysis outputs; and
- schema/software versions.

This package is the key handoff artifact if direct Department-system integration is impossible.

### 5. State delivery UX

Only after the first four are stable should the desktop workflow be reorganized around:

1. **New Research Requirement**
2. **Import or Collect**
3. **Review Search Plan**
4. **Run / Monitor Coverage**
5. **Review Evidence and Findings**
6. **Export Brief / Evidence Package**
7. **Save as Monitor / Compare with Prior Run**

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

