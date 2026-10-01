# Operations runbook

For the person who keeps a SUGAR installation running after the original team has left.

## What runs where
- **Desktop app:** a local research service starts with the app; projects are folders on that computer.
- **Server (optional):** `python sugar_api.py --host ... --port ... --generate-token` serves the same API. Scheduled monitoring runs in this process.
  Set `SUGAR_DISABLE_SCHEDULER=1` to turn the scheduler off.
- **Projects** hold everything: plans, runs, items, registry, review log, digests. Back up the project folders.

## Keys and cost
- Add an AI provider (OpenAI or Virginia Tech ARC, or others) under Settings. Keys go to the operating system's credential store, never into a project.
- Each run has a soft **model-call budget** (Advanced → Limits, default 500, 0 = unlimited). When spent, optional AI steps pause with a notice; collection and the run continue.
- Coding, relevance and institution scans take a smaller per-action budget (default 30 to 40 calls).
- Platform keys (X, Mastodon, Bluesky, optional OpenAlex) are under Settings → Platform credentials. Wikipedia, news (GDELT), the web reader and feeds need none.

## People and permissions
Roles: viewer (read), reviewer (judge, tag, comment, verify claims), analyst (collect, record institutions), owner (settings, profiles, members). Issue and revoke member tokens from the project page. Provider keys, diagnostics and folder access are administrator-only.

## Routine checks
- **Weekly:** open Monitoring; read the latest digest; resolve any source marked incomplete.
- **After changing a model or vocabulary:** run Accuracy check on a fresh sample and keep the numbers.
- **Quarterly:** re-verify high-importance institutions (last-verified dates are on every record) and re-check page history for closures.

## When a source stops working
Social platforms change access without notice. A failing source is reported per run with its reason and a Retry button.
Sources that use stable public interfaces (Wikipedia, GDELT, OpenAlex, feeds, websites) fail rarely and with a clear message (rate limit,
robots.txt refusal, unreachable site). A rate limit is retried automatically; a refusal is not worked around.

## Data handling
- Collect only public material. SUGAR identifies itself in its User-Agent and follows `robots.txt`.
- Exports can contain public posts with author names. Decide a retention period for projects and delete old projects you no longer need.
- Profiles and briefs contain no credentials. Check a brief before sharing it: it quotes public sources and names institutions.

## Troubleshooting
| Symptom | Likely cause | Fix |
|---|---|---|
| "Could not reach the SUGAR API" | Service not running or wrong address | Settings → Connection |
| An AI provider says "key rejected" | Wrong key or no access to the model | Settings → LLM providers → Test connection |
| Institutions are not on the map | No coordinates recorded | Institutions → "Place n on the map" (uses a public geocoder, one request per second) |
| A web page returns nothing | robots.txt, login wall, or script-rendered page | Add a feed or a different page; SUGAR will not bypass either |
| Monitoring does not run | App closed, or another run is active | Keep SUGAR open or run the server; use "Run now" |

## Updating
Update SUGAR, then open a project and run one pass of each monitor. Registry, review and digest files are append-only and forward compatible.

## Baseline packs

The program ships the sync *engine* only. Which directories to pull, and how their fields and status wording map to registry
fields, are described in a **baseline pack**: a JSON object `{"sources": [spec, ...]}` kept outside the repository.

Where packs are found (first match per source key wins): the project's `references/baseline_packs/`, the path in
`SUGAR_BASELINE_PACKS`, then `<SUGAR_HOME>/baselines/`. `sugar-project sync-baselines <workspace> --pack pack.json` also takes
a file directly, and the Institutions page's **Sync official baselines** button uses the installed packs.

A spec has: `key`, `network`, `role` (`subject` or `reference`), `endpoint` (https), optional `landing_url`, `params`,
`rows_path`, `id_field`, `id_prefix`, a `fields` map from registry columns to source fields, optional `exclude` rules, a
`status` rule (`field`, `map`, `default`; unmapped wording stays `unknown`), `detail_url` template, `description` parts,
`coverage_limits` and `license_notes`.

Each sync stores the raw response, a normalized CSV and a manifest under `references/official_baselines/snapshots/<time>/`,
and imports records with stable IDs, so repeating a sync updates rather than duplicates. Only public https addresses are read.
