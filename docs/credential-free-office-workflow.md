# Credential-free office workflow

SUGAR remains a Tauri 2 desktop application with a shared Python engine. The
Research page now contains a **What changed** banner and an **Evidence desk** in
basic mode. Advanced Overview also shows the desk. All seven operations below
work without an external account, model provider, or API key.

## 1. Activity-status proposals and imports

Each institution has a separate activity assessment; it does not replace its
recorded status or human verification. The six display labels follow Group 1's
section 10 methodology supplied by the project team:

| Assessment | Registry status | Activity confidence | Required basis |
| --- | --- | --- | --- |
| Active, high confidence | active | high | Current-year official program evidence |
| Active, medium confidence | active | medium | Evidence in the 2024–present window without current official programming |
| Status unclear | unknown | low | Insufficient or conflicting evidence |
| Closed | closed | high | A human-verified registry lifecycle claim |
| Renamed/restructured | renamed | high | A human-verified registry lifecycle claim |
| Relocated | relocated | high | A human-verified registry lifecycle claim |

The current year follows the assessment date. Publication dates, structured
event dates, explicit advertised terms such as “Autumn 2026,” known-account
posts, and news mentions retain their separate meanings. A stated term does not
invent an exact day. Future publication dates, retrieval dates and archive
capture dates do not substitute for evidence of completed activity. Cancellation
and historical wording prompt review. Pattern checks are conservative proposals,
not independently validated status findings.

Add institution-specific official URL roots under **Public links**. The detail
drawer can add a source as an official root. Shared university roots should name
the relevant department path. Previously collected pages within those URL scopes
and exact institution-name news mentions are matched locally and marked as
automatic candidates. No registry association is silently verified. Manually
linked evidence is also included. A new import is assessed immediately from
already collected material, without network or model calls.

The **Page history** action persists Wayback results with the activity assessment.
Captures indicate archive availability, not active operations. Reads and local
assessment refreshes do not request archive history again.

The importer maps `Open` to `active`, `TBD`/`unclear` to `unknown`, both Active
confidence labels to `active`, and `Renamed/restructured` to `renamed`. Original
wording remains in `reported_status` provenance. `Suspended` and `merged` remain
unverified `unknown` pending resolution of the two inconsistent source scales;
the original words are retained. `affiliation_type` is a separate importable
claim, never part of activity status. Importing a claimed active status alone
does not establish current activity.

## 2. Priorities, audience coding and terminology

Local pattern coding runs automatically after collection/reprocessing and saved
page import. Imported institution rows receive separate row-wording proposals.
**Refresh local assessments** codes older saved results without recollecting them.

The proposed A–D rubric gives strategic policy/commercial priorities precedence
over leader/sector programs, education, and generic cultural programming. These
are editable study rules, not a claim that the sponsor approved exact thresholds.
Unmatched material remains uncoded. Results can filter by tier and audience;
choosing a tier does not delete other items.

The six audience groups are `students`, `k12`, `teachers`,
`technical_professionals`, `officials`, and `business`. Detailed existing audience
codes remain available. Grounded optional model proposals can map to these fixed
groups through the existing taxonomy; local coding needs no model. Inspect an
item to confirm/reject its source-quoted codes. Human decisions survive reruns.
New priority proposals supersede old automated tiers. Earlier confirmed rubric
versions remain labeled for review; confirming a replacement tier records the
prior tier's rejection. Old evidence and decisions remain in the event history.
Attendance remains **as reported by the source**, not independently verified
reach. Program priorities do not measure influence or public opinion.

Edit/download/load **study-rubric.json** in the desk, or edit that plain file in
the project's `research` directory. It contains tier terms, audience terms,
multilingual program aliases, and optional `alert_terms`. Every rule proposal
records its version, fingerprint, matched term and source quote. The file also
travels in method profiles and analysis exports. Invalid optional configuration
does not take down the map; the desk reports that it needs repair.

## 3. Country snapshot and offline map

Choose a country in the desk and select **Country snapshot (.html)**. The Map
page offers the same button after choosing a country in Filters. The standalone
HTML includes an offline land map, numbered institution locations, activity
assessments, recent programs/mentions from the past 365 days and explicitly dated
current/scheduled programming, narrative review
candidates, coverage gaps and evidence links. It uses recorded WGS84 coordinates;
unplaced institutions remain in the table. Approximate city/country placements
do not become exact sites. The bundled Natural Earth land polygons require no
tiles, scripts, installation or network access to render.

**Country analysis bundle** adds full scoped evidence, CSV/JSONL, GeoJSON, coding
events, a rubric and a SHA-256 manifest. Country mentions remain distinct from
items linked to institutions and automatic URL/name association candidates; a
mention is not an origin location.

Narrative candidates come from analyst review tags (`anti_us`, `narrative_flag`)
or explicitly configured alert terms. Keyword matches do not establish intent.
For linked, placed institutions, the snapshot attaches nearest recorded embassy
and American Space candidates from networks marked **reference**, using their
names, coordinates and source URLs. Missing references are reported as coverage
gaps. Proximity is not jurisdiction. Nothing sends an alert or contacts anyone.

Run `python examples/keyless-office-demo/build_demo.py` for a clearly labeled,
synthetic Mexico demonstration and offline files. It never modifies an existing
project and makes no network calls.

## 4. Keyless feed seeds

The feed helper builds YouTube channel RSS and regional Google News search RSS
URLs. It also finds valid `/channel/UC…` accounts already recorded in the registry.
Preview, save, then enable RSS in your research plan. Publisher/channel titles
can supply the institution search context; the match basis is exported. YouTube
entries retain descriptions, video content type and channel provenance so they
can support known-account activity signals.

Use a real 24-character channel ID; handles are not resolved by an extra service.
YouTube feeds provide recent video entries, not comments or a complete archive.
Google News RSS is best effort, with variable outlet and regional coverage.
Neither is presented as a guaranteed bulk historical dataset. No platform
research-access application or sponsor data-sharing permission is assumed.

## 5. Analyst capture inbox

Drop/select 1–20 saved HTML files totaling at most 25 MB, or choose a folder.
Provide the original URL for a single file; batch pages need a canonical/og:url
in their HTML. Alternatively place files under `research/capture-inbox` and select
**Scan project inbox**; a `page.html` can have a `page.url.txt` sidecar. The folder
scanner reads at most 20 new files per pass and skips symlinks and files over 5 MB.
Repeated unchanged pages are skipped rather than creating duplicate result runs.

The existing saved-page sanitizer removes executable/hidden/control content and
credential-like values. Original HTML is not retained by uploads. Imported visible
text becomes a normal saved result with provenance and local coding. Files put
in the project drop folder remain under analyst control; scanning does not delete
them. This does not automate login or bypass source access controls.

## 6. What changed and monthly refreshes

The Research banner and desk surface the latest digest. Digests compare registry
snapshots and now record newly proposed/confirmed program/audience codes and
narrative review candidates. A first pass establishes a baseline. Repeating a
check without changes produces no new changes.

Use the existing **Monitoring** page to choose **Monthly** (720 hours) for the
saved plan. The local scheduler runs while the SUGAR engine is running; it is not
an always-on hosted service. Optional provider usage follows that saved plan;
choose **No AI** for a fully keyless collection plan. No new schedule is enabled
without the analyst selecting it.

## 7. Approved-tool export

**Export for approved AI tool** packages saved evidence, coding/human decisions,
the rubric and `approved-tool-prompt.txt`. Run exports also include these files.
The prompt requests item/URL/date/run citations, explicit unknowns, coverage limits,
and human adjudication; source text is data, not instructions. The analyst chooses
whether/where to upload it. SUGAR does not claim a particular external tool is
approved for a specific organization or data classification.

## Sources and limits

- Wayback API documentation: https://archive.org/help/wayback_api.php
- Natural Earth public-domain terms: https://www.naturalearthdata.com/about/terms-of-use/
- Local methods are auditable heuristics. They do not independently authenticate
  a publisher or validate a source's stated attendance, program reach or intent.
- The workflow does not depend on platform research credentials, and does not
  assume that academic research-access terms permit transfer to a sponsor.
