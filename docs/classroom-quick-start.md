# SUGAR Classroom Quick Start

This guide is for a first-time user who wants to get useful results without learning every SUGAR feature first.

## The 5-minute path

For a real research assignment, start from the question rather than a keyword box:

1. **Create a Research Project.** On Windows open **State Workflow -> Research Project**. On macOS open **Research Project**. Choose a project folder that can travel with the work.
2. Enter the **research question**, geography, target audiences, known entities, languages, timeframe, and preferred sources. Save the requirement.
3. Click **Compile Deterministically** to turn the prose question into an inspectable research strategy. Optionally use **Compile + AI** to enrich semantic interpretations and search hypotheses. AI is not required.
4. Review the compiled strategy. Explicit source-span concepts remain tied to the exact words you wrote; interpreted concepts, search hypotheses, and research dimensions can be edited or excluded. Enter a named reviewer and click **Approve Research Strategy**.
5. Click **Build Search Plan from Approved Strategy**. The plan records which approved strategy produced it and remains inspectable rather than hidden inside an agent loop.
6. Run the plan with a small initial collection, or import an existing authorized CSV/JSONL dataset.
7. If you need AI assistance for evidence triage or synthesis, configure an LLM key in **Settings**. Then **Prepare State Assessment Suggestions**, **Export Human Review Workbook**, make the named analyst decisions in that workbook, save it, and click **Apply Human Review**. Only after that should you export the **Verified Handoff**. The bundle carries the requirement, approved compiled strategy, plan, evidence, reviewed observations, assessments, provenance, limitations, and lineage together.

For a fast collector sanity check rather than a research project, **Collect -> Quick Search** on Windows or **Expert Search** on macOS is still available.

## What the pages are for

- **Home** — status, workflow map, and first-run shortcuts.
- **Collect** — normal keyword collection and resumable larger harvests.
- **Weibo** — investigate a known public Weibo post or run repeatable Weibo qualification/coverage checks.
- **Public URL** — import a specific known public item without pretending it is searchable. This is the supported path for public WeChat Official Account articles.
- **State Workflow** - the Windows home for the question-first Research Project plus expert assessment/review tools.
- **Intelligence** — deterministic tradecraft checks and optional LLM-assisted synthesis. Use this after you have a real corpus.
- **Maps & Reports** — turn existing results into maps, PDF, or Word outputs.
- **Settings** — ARC/model connection, optional source credentials, and output defaults.

## Credentials: what is actually required?

**LLM API key:** optional. Use OpenAI, Virginia Tech ARC, or a compatible custom provider when you want AI semantic compilation, translation, location inference, AI triage, or synthesis. Deterministic requirement compilation, project/import/review/export workflows, and ordinary collection do not require an LLM.

**Bilibili:** no source credential is required for the supported public collection path.

**Weibo:** supported public surfaces can be used without a saved session. An authorized existing Weibo session is optional and may improve access to surfaces that are otherwise limited.

**WeChat Official Accounts:** use **Collect -> Public URL** with an ordinary public `https://mp.weixin.qq.com/...` article URL. SUGAR does not provide WeChat keyword search, private-chat collection, Mini Program collection, automated login, or challenge bypass.

**X / Bluesky / Mastodon:** optional general-source adapters. Only configure their credentials if you intentionally plan to use those sources.

SUGAR does not create accounts, bypass authentication, rotate identities, or defeat platform access controls.

## A sensible first exercise

Search one or two narrow terms on Bilibili with a small page limit. Inspect what was actually collected. Then decide whether you need translation/inference, a larger resumable harvest, a post-level Weibo investigation, or downstream analysis. Do not begin with every source and every enrichment option enabled.

## Windows command line

The portable Windows folder also includes command wrappers backed by the same bundled SUGAR engine:

```bat
sugar.cmd --help
sugar-project.cmd --help
sugar-state.cmd --help
sugar-intel.cmd --help
```

This does **not** require a separate Python installation. The GUI is best for discovery and classroom use; the CLI is useful for reproducible or scripted workflows.

## Terminology

- **Audit** means checking whether evidence/verification rules were followed.
- **Compare assessment versions** means showing what changed between two saved assessment snapshots (the operation is often called a “diff” in developer tools).
- **Qualification** means measuring collector coverage, failures, access limits, provenance, duplicates, and repeatability. It is not an official certification or authority-to-operate.
- **Observation** is collected evidence. **Assessment** is an analytic judgment linked to evidence. SUGAR deliberately keeps those separate.
- **AI-triaged** means a provider/model/workflow generated a suggestion. It is not human verification. SUGAR records the provider, model, workflow version, reviewer, and review state separately.


## Live-source reliability note

For a first Bilibili run, use one search term, 20 posts per query, and one page. Quick Search disables per-result Bilibili detail hydration so a classroom test does not create a large burst of requests. Bilibili may still deny anonymous search under its current access/risk-control policy; if that happens, stop and retry later rather than repeatedly retrying. Weibo keyword search requires an existing authorized Weibo session.
