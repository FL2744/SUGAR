# Research Requirement Compiler

The Research Requirement Compiler turns a natural-language research question into an inspectable, analyst-approved research strategy before SUGAR generates a search plan.

It preserves three epistemic classes and never treats them as interchangeable:

1. **Explicit** - text the analyst actually wrote. An explicit concept must carry an exact source span into the original question.
2. **Interpreted** - a semantic interpretation that helps operationalize the question but is not a literal analyst-stated fact.
3. **Hypothesis** - something worth searching for. It is neither a finding nor an analyst-stated fact.

## Artifacts

The workflow keeps three separate artifacts:

| Artifact | Meaning |
| --- | --- |
| research-requirement.json | What the analyst asked and any explicit form constraints |
| research-strategy.json | How SUGAR compiled/interpreted the requirement, with analyst review state |
| search-plan.json | Executable bounded query branches produced from the approved strategy |

Changing a search hypothesis must not rewrite the original research question, and an AI-generated interpretation must not become an analyst-stated requirement simply because it was saved to disk.

## Deterministic compile

The deterministic compiler requires no LLM. It preserves the original question, incorporates analyst-supplied constraints, identifies common question structures and activity verbs, extracts safe exact source spans, classifies the broad analytic task, creates observable research dimensions, and reports missing dimensions.

For a question such as "How are foreign educational institutions reaching university students in Exampleland?" the deterministic compile can identify the subject, the activity "reaching", the audience "university students", the geography "Exampleland", and a mechanism-assessment task.

Every explicit concept carries character offsets. Loading the strategy re-validates those offsets against the stored original question.

## Optional AI semantic compile

AI expansion is optional. The configured OpenAI, Virginia Tech ARC, or custom OpenAI-compatible model receives the original question, the analyst-supplied structured requirement, and the deterministic compile. Its task is to improve semantic coverage, not answer the research question.

The model returns separate explicit concepts, interpreted concepts, search hypotheses, and research dimensions. SUGAR deterministically validates the response. A proposed explicit concept is accepted only when its source text and offsets exactly match the original question. Invalid spans are discarded. Hypotheses cannot carry source spans and therefore cannot masquerade as analyst-stated facts.

The compiled artifact records AI provider, model, and compiler workflow version when AI expansion was used.

## Analyst review

The strategy begins in draft state. Both desktop applications expose it before planning. Explicit concepts are immutable source text; interpreted concepts and hypotheses can be edited; any concept can be included or excluded; rationales, research dimensions, missing fields, and the analytic task are visible; and deterministic versus AI-assisted compile are separate actions.

Approval requires a named reviewer. Approval, concept edits, inclusion decisions, analytic-task edits, and analyst-added concepts are appended to strategy event history. Editing an approved strategy returns it to draft and requires re-approval.

## Strategy-aware planning

If no compiled strategy exists, the legacy deterministic planner remains available for compatibility. Once a strategy artifact exists for a requirement, the project workflow refuses to consume it while it is unapproved.

After approval, the planner generates bounded branches from approved subjects/entities and geographies, subjects and target audiences, activities, observable indicators from approved research dimensions, and included analyst-approved search hypotheses.

Hypothesis branches are explicitly labeled in their rationale as search hypotheses rather than asserted facts. The search plan records a compiled_strategy_plan event containing strategy ID and reviewer. If the research question changes and creates a different requirement ID, the old strategy is rejected as stale.

## Portable handoff

When a project uses an approved strategy, the portable handoff includes context/research-strategy.json. The manifest records its schema and strategy ID.

Handoff verification checks semantic linkage in addition to hashes: the strategy must be human-approved; its requirement ID must match; its strategy ID must match the manifest; and the search plan must link to the same strategy. Recomputing hashes after breaking those links does not make the bundle valid.

## CLI

Compile deterministically: sugar strategy compile research-requirement.json --output research-strategy.json

Compile with AI: sugar strategy compile research-requirement.json --ai-expand --provider openai --model gpt-5.6-luna

Inspect: sugar strategy show research-strategy.json

Apply structured analyst edits: sugar strategy update research-strategy.json --edits strategy-edits.json

Approve: sugar strategy approve research-strategy.json --reviewer "Analyst One" --note "Interpretation checked."

Build the strategy-aware plan: sugar plan research-requirement.json --strategy research-strategy.json --output search-plan.json

When a workspace is supplied, plan automatically discovers the registered research_strategy artifact.

## Design rule

The compiler may help answer: **What does this question ask us to investigate?**

It may not answer: **What is true about the world?**

The latter requires collected evidence, source-grounded observations, analytic assessment, and human review.
