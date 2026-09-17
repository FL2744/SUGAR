# SUGAR Classroom Quick Start

This guide is for a first-time user who wants to get useful results without learning every SUGAR feature first.

## The 5-minute path

1. **Open Settings.** Choose **Virginia Tech ARC**. Click **Get ARC API Key**, sign in with your VT account, create a personal key, paste it into SUGAR, and click **Test ARC Connection**.
2. **Open Collect → Quick Search.** Start with **Bilibili** and/or **Weibo**. Enter a few search terms, one per line.
3. Leave **Source credentials** blank unless your specific task requires an authenticated source. Basic public Bilibili work is designed to operate without X, Bluesky, or Mastodon credentials.
4. Keep the first search small. Run it and watch **Activity & Outputs** at the bottom of the window.
5. Open the generated CSV/XLSX/JSONL outputs before moving on to advanced analysis.

## What the pages are for

- **Home** — status, workflow map, and first-run shortcuts.
- **Collect** — normal keyword collection and resumable larger harvests.
- **Weibo** — investigate a known public Weibo post or run repeatable Weibo qualification/coverage checks.
- **State Workflow** — turn normalized observations into reviewable assessments, change reports, templates, and briefing packages.
- **Intelligence** — deterministic tradecraft checks and optional LLM-assisted synthesis. Use this after you have a real corpus.
- **Maps & Reports** — turn existing results into maps, PDF, or Word outputs.
- **Settings** — ARC/model connection, optional source credentials, and output defaults.

## Credentials: what is actually required?

**Virginia Tech ARC API key:** recommended for classroom use when you want translation, location inference, AI triage, or synthesis.

**Bilibili:** no source credential is required for the supported public collection path.

**Weibo:** supported public surfaces can be used without a saved session. An authorized existing Weibo session is optional and may improve access to surfaces that are otherwise limited.

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


## Live-source reliability note

For a first Bilibili run, use one search term, 20 posts per query, and one page. Quick Search disables per-result Bilibili detail hydration so a classroom test does not create a large burst of requests. Bilibili may still deny anonymous search under its current access/risk-control policy; if that happens, stop and retry later rather than repeatedly retrying. Weibo keyword search requires an existing authorized Weibo session.
