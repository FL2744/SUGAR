# SUGAR Agentic Intelligence: Deep-Mode Architecture

This supplement documents the iterative reasoning architecture introduced after the first State analytic-intelligence design. It should be read with `docs/state-analytic-intelligence.md`.

## Why deep mode is different

Deep mode is not merely a request for a longer model response. It changes how evidence is selected and how agents are forced to revisit their own conclusions.

The current sequence is:

**full deterministic evidence index -> bounded specialist prompt -> first-pass judgment -> evidence-neighborhood retrieval -> specialist reassessment -> integration -> red-team attack -> revised integration**

The system keeps a broad case/evidence index for validation and retrieval while deliberately bounding the number of full cases placed into any one specialist prompt. This avoids two common failure modes:

1. stuffing the entire corpus into a model and receiving shallow averaging; and
2. trimming the corpus so aggressively that a country specialist can discover a useful case but the final integrator cannot validate the evidence reference.

## Evidence-neighborhood refinement

After the first specialist pass, SUGAR extracts the evidence references the agent actually relied upon.

For each cited case, deterministic comparable-case links are used to retrieve a local evidence neighborhood. The same specialist is then asked to reassess the first-pass explanation against this new neighborhood.

The refinement instruction explicitly asks the agent to:

- find cases that weaken its original explanation;
- revise confidence when warranted;
- remove judgments that do not survive the additional evidence;
- preserve contrary evidence rather than rationalizing it away.

This is a targeted self-challenge mechanism. It is more useful than simply asking a second model to disagree in the abstract because the challenge introduces additional corpus evidence selected from measured case similarity.

A comparable case remains a **retrieval lead**, not proof of shared direction, common sponsorship, coordination, or influence.

## Tradecraft audit before synthesis

Run the deterministic audit directly:

```bash
sugar-intel tradecraft observations.xlsx state.reviewed.jsonl \
  --output tradecraft.json
```

The audit evaluates the structure of the evidentiary base without asking an LLM to judge source truthfulness.

### Source adequacy

Each observation receives a structural adequacy description based on:

- number of auditable evidence identities;
- source types;
- platforms;
- source domains;
- diversity of source channels;
- evidence date range;
- dependence on one source type or one web domain.

Labels include:

- `multi_source_diverse`;
- `multi_evidence_limited_diversity`;
- `single_evidence_identity`;
- `no_auditable_evidence_identity`.

These labels describe corroboration structure. They are **not source credibility scores**.

Three outlets repeating one press release are not necessarily three independent confirmations. Conversely, one authoritative primary document can sometimes be stronger evidence for a narrow fact than many derivative articles. Human review remains necessary.

## Analytic tensions

SUGAR flags combinations that deserve explicit analyst attention. Current examples include:

- a human-verified State assessment built over an unverified underlying observation;
- confirmed sponsor support resting on only one evidence identity;
- support/coordination/influence claims with weak corroboration;
- `causal_influence_evidence` without a human-verified influence claim;
- high reach/engagement without outcome evidence;
- an `anti_us` tag without a verified narrative claim;
- cross-state/third-party coordination tagging without a verified coordination claim;
- a material U.S.-overlap result whose stored fields do not expose the basis.

These are **tensions, not automatic errors**. Their purpose is to stop convenient coding combinations from disappearing into polished prose without scrutiny.

## Epistemic debt

The audit also tracks unresolved analytical obligations:

- possible/probable sponsor-support assessments still pending review;
- high/urgent-priority assessments not yet verified;
- unresolved geographic attribution;
- high-consequence support/coordination/influence claims still unverified.

This is called *epistemic debt* because unresolved items accumulate analytical risk. A sponsor-facing synthesis should not merely report conclusions; it should make visible which conclusions remain expensive to trust.

## How agents use the audit

The tradecraft audit is inserted into the packet seen by specialist agents and into deep-mode evidence neighborhoods.

That means the methodologist and other specialists can directly see that, for example:

- a striking pattern depends mostly on one source type;
- the apparent coordination cases have weak corroboration;
- a country comparison has asymmetric verification;
- high engagement is present but outcome evidence is absent.

The audit does not force a conclusion. It changes the evidence context in which conclusions are generated.

## Consensus is not correctness

SUGAR does not treat agreement among agents as independent confirmation. Agents may share the same model family, prompts, evidence packet, and blind spots.

The value of multiple agents is **functional decomposition**:

- one looks for system patterns;
- one looks for network mechanisms;
- one evaluates comparative validity;
- one focuses on public-diplomacy implications;
- one focuses on trajectory/signposts;
- one attacks methodology;
- country/case agents provide local depth;
- the red team attacks the integrated draft.

A judgment is stronger because of its evidence, corroboration, explanatory resilience, and handling of alternatives—not because several model calls repeated it.

## Recommended use

Use `quick` when exploring a newly collected dataset.

Use `standard` for routine analytical updates when the corpus is mature enough to support structured reasoning.

Use `deep` for important sponsor updates, mature country portfolios, or research questions where the cost of a shallow synthesis is higher than the cost of additional model calls.

Do not use deep mode to manufacture certainty from sparse evidence. When the evidence base is thin, the correct deep-mode result may be a better collection plan rather than a stronger judgment.
