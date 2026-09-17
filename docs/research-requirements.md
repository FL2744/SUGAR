# Research requirements and bounded search plans

The State-facing workflow should begin with the analyst's information need, not a manually authored keyword matrix.

## Research requirement

`ResearchRequirement` schema 1.0 stores the question, geography, timeframe, target audiences, languages, known entities, exclusions, preferred sources, and collection mode (`quick`, `standard`, or `deep`).

```bash
sugar requirement create \
  --question "How are foreign educational opportunities reaching university students in Exampleland?" \
  --geography Exampleland \
  --audience "university students" \
  --language Regional Language \
  --language Examplean \
  --known-entity "Public Engagement Center A" \
  --known-entity "Cultural Center B" \
  --since 2026-01-01 \
  --until 2026-09-17
```

When a workspace is active, the requirement is stored in the State workspace area and registered as a `research_requirement` artifact.

## Search plan

```bash
sugar plan research-requirement.json

# Optional provider-neutral model expansion; generated branches remain bounded/audited.
sugar plan research-requirement.json --ai-expand --provider openai
```

The initial deterministic planner deliberately does only what it can explain without a model: it seeds known entities and scoped geography combinations. If no known entities exist, it creates a clearly labeled discovery fallback from the research question.

Every `SearchBranch` stores a query, rationale, origin, status, search family, language, generator identity, parent, parent concept, evidence IDs, hop depth, metrics, and stable branch ID. Model-assisted planning may propose branches, while the deterministic controller remains responsible for budgets, exclusions, deduplication, and auditability.

## Drift controls

Discovered branches must cite evidence IDs and attach to an existing parent branch. The plan enforces a mode-specific maximum hop depth and branch budget. An analyst can set branch status to planned/approved/active/paused/retired/excluded/completed, with each change recorded in the plan event log.

The deterministic controller evaluates branch metrics including relevance, novelty, duplication, and coverage gain. It can continue, retire, or route a branch to human review. This prevents an LLM from silently wandering multiple conceptual hops away from the original requirement.


## Executable adaptive loop

The current core supports the research loop as separate inspectable operations rather than one opaque autonomous agent:

```bash
# 1. Execute currently runnable branches through the ordinary collector registry.
sugar collect-plan research-requirement.json search-plan.json --sources bilibili,weibo

# 2. Triage/review the collected canonical data into ResearchObservations.
sugar triage social_search_posts_YYYYMMDD_HHMMSS.csv --output observations.csv

# 3. Feed relevance decisions back into branch metrics and stopping rules.
sugar plan-feedback search-plan.json social_search_posts_YYYYMMDD_HHMMSS.csv observations.csv

# 4. For a useful branch, ask the model for evidence-grounded pivots using original source text.
sugar expand-plan research-requirement.json search-plan.json \
  social_search_posts_YYYYMMDD_HHMMSS.csv observations.csv \
  --branch q_example --provider openai
```

`plan-feedback` counts only `relevant` and `not_relevant` observations as decisive relevance assessments. `uncertain` remains explicitly tracked and cannot silently become negative evidence. `expand-plan` supplies original collected source text to the planner and accepts only evidence IDs that actually exist in the supplied observations. A fabricated evidence ID is rejected.

This separation is intentional: collection can run without an LLM; human-coded observations can drive the same feedback controller; and a model service can be changed without changing the requirement, evidence, or stopping-rule schemas.
