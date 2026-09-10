![sugar logo](sugar-logo.png)
# SUGAR: System for User-Generated Content Gathering, Analysis, and Representation

`SUGAR.py` is a menu-driven research program. Its independent workflows search
public posts, map an existing SUGAR CSV/XLSX file, or analyze an existing file
as a polished Word or PDF report. Search supports X, Bluesky, Mastodon, or a
user-selected combination and can translate terms and posts and infer broad
public locations.

The main menu keeps collection separate from downstream work:

1. Run a new social-media search
2. Map an existing CSV/XLSX results file
3. Analyze an existing CSV/XLSX results file
4. Exit

Report generation is implemented separately in `sugar_analysis.py`, keeping the
analysis and document-rendering code out of the collectors.

The default `api` mode prompts for social-data sources. X can use its official
recent-search or full-archive endpoint; Bluesky uses its public AppView search;
Mastodon searches the statuses known and indexed by a user-selected server. A
legacy `saved_html` mode remains available for previously saved Nitter pages.

## Native macOS application

`SUGAR-macOS` contains a native SwiftUI application for people who should not
need Terminal, Python, or a virtual environment. It provides separate Search,
Map, Analysis, and Settings screens, stores service credentials in macOS
Keychain, and calls a bundled self-contained SUGAR backend.

The included scripts build an Apple Silicon test application and DMG with the
current command-line toolchain. Public distribution additionally requires an
Apple Developer Program membership, full Xcode, a Developer ID Application
certificate, and notarization credentials. See `SUGAR-macOS/README.md` for the
complete signing, notarization, stapling, and release procedure.

## What it creates

Every run creates one local timestamp in `YYYYMMDD_HHMMSS` format and applies it
to all primary output filenames. For example, a run started at 2:30:12 p.m. on
August 29, 2026 can produce:

- `social_search_posts_20260829_143012.csv` containing collected and enriched data
- `social_search_posts_20260829_143012.xlsx`, a formatted Excel workbook
- `social_search_posts_20260829_143012_map.html`, an interactive map created
  from a selected existing results file
- `social_search_posts_20260829_143012_analysis.docx` and/or `.pdf`, a descriptive
  analysis report with collection diagnostics, charts, engagement measures,
  vocabulary, caveats, and recommendations
- A local geocoding cache

Search writes the CSV and Excel workbook only. Mapping and analysis are launched
separately from the menu and prompt for an existing file, so either operation can
be repeated without rerunning or paying for a search. `geocode_cache.json`
deliberately retains a stable name because it is a reusable support cache rather
than a run result.

Inferred locations are broad, model-generated estimates. They are not verified
geotags and should not be treated as precise personal locations.

The interactive map retains its clustered post markers and also provides
weighted activity heatmaps for posts dated within the last 7, 30, 90, and 365
days. The 30-day heatmap is visible initially; each window can be independently
toggled in the map's layer control. Counts use successfully geocoded posts and
the `date_iso` timestamp relative to the time the map is generated.

## First-time setup

Open Terminal, change to your project directory, and create a virtual Python
environment:

```bash
cd "your project directory"
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 SUGAR.py
```

The script checks for its Python packages and installs missing ones into the
active virtual environment. Internet access is required for package installation,
LLM requests, live page retrieval, geocoding, and map tiles.

## X API authentication

For `x_api` mode, the script loads the **App-Only Bearer Token** from the hidden
`.x_bearer_token` file in the SUGAR directory. The file must contain only the
token and is protected with owner-only permissions (`chmod 600`).

The token is not printed, written into `SUGAR.py`, or included in CSV, Excel,
map, or cache files. `.x_bearer_token` is excluded by `.gitignore`; never share
or commit it to version control.

At startup, choose either:

```text
GET https://api.x.com/2/tweets/search/recent
GET https://api.x.com/2/tweets/search/all
```

Full-archive search requires eligible Pay-per-use or Enterprise access. The
script also prompts for an optional inclusive UTC date range and zero or more
post-language filters. Multiple languages are combined as an X query group such
as `(lang:en OR lang:fr)`. X charges for API resources returned, so start with
small values for `MAX_POSTS_PER_QUERY` and `MAX_PAGES_PER_QUERY`, configure a
spending limit in the Developer Console, and monitor usage.

## Bluesky search

Bluesky public search normally requires no API key. The script first offers a
choice: press Enter to use the public endpoint, or enter a Bluesky handle/account
email and a dedicated Bluesky app password. The public endpoint is:

```text
GET https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts
```

It supports keyword search, date bounds, up to 100 results per request, and
cursor pagination. Bluesky's search syntax and ranking are not identical to X,
so an advanced X query may not have the same meaning on Bluesky.

Some institutional or filtered networks block the `*.bsky.app` API hosts and
return an HTML `403 Forbidden` page. For that situation, create a dedicated app
password in **Bluesky Settings > Privacy and Security > App Passwords**, then
enter your handle and that app password at startup. SUGAR signs in through
`bsky.social` and sends search requests through Bluesky's authenticated AppView
proxy. Use an app password only—never your main account password.

The app password and temporary access token remain in memory for the current
run. They are not printed or written to the CSV, Excel, map, cache, or project
files. You can revoke the app password later from the same Bluesky settings page.

## Mastodon search

Mastodon is decentralized. The script asks for a server URL, defaulting to
`https://mastodon.social`, and searches that server through:

```text
GET /api/v2/search?type=statuses
```

This is not a global search of the entire Fediverse. Results depend on which
remote posts the selected server knows about, whether it has full-text search
configured, and whether authors opted into public indexing.

The script accepts an optional Mastodon user access token through hidden input.
Authenticated search generally provides better full-text status access and
allows offset pagination. A token must include permission to read/search public
statuses on that server. It is held only in memory and is never saved.

## Normal startup after the first run

From your project directory:

```bash
source .venv/bin/activate
python3 SUGAR.py
```

When finished, leave the virtual environment with:

```bash
deactivate
```

## Choose an LLM provider

When translation or location inference is enabled, the script asks you to
choose one of two providers.

### OpenAI API

The OpenAI menu offers:

1. `gpt-5.6-luna` — default; intended for cost-sensitive, high-volume work
2. `gpt-5.6-terra` — balances capability and cost
3. `gpt-5.6-sol` — flagship capability
4. A different OpenAI model ID entered by the user

Enter an OpenAI Platform API key when prompted.

### Virginia Tech ARC LLM API

The ARC menu offers:

1. `gpt-oss-120b`
2. `DeepSeek-V4-Flash`
3. `GLM-5.2`
4. `Kimi-K3`
5. A different ARC model ID entered by the user

The script uses ARC's OpenAI-compatible endpoint at
`https://llm-api.arc.vt.edu/api/v1`. Virginia Tech students, faculty, and staff
can create a personal API key at <https://llm.arc.vt.edu/> under **User profile
> Settings > Account > API keys**.

For both providers, key input is hidden. The key is retained only in memory for
the current run and is not written into the script or output files. Never share
an API key.

## Configure a run

The main settings are near the top of `SUGAR.py`:

- `MODE`: use `"api"` to choose X, Bluesky, Mastodon, or a combination; use
  `"saved_html"` for previously saved Nitter pages
- `SAVED_HTML_FILES`: input pages used in saved-HTML mode
- `TARGET_LANGUAGE`: translation target
- `SINCE_DATE` and `UNTIL_DATE`: defaults for optional date bounds; X prompts for
  an inclusive date range at startup
- `MAX_POSTS_PER_QUERY` and `MAX_PAGES_PER_QUERY`: collection limits
- `TRANSLATE_POSTS`: enable or disable post translation
- `INFER_LOCATIONS`: enable or disable model-based location inference
- `CREATE_MAP`: retained internally and disabled by default because mapping is a
  separate main-menu workflow
- `DEFAULT_SEARCH_TERMS`: terms offered at startup; enter one or several terms,
  one per line

For X, the startup flow additionally selects recent or full-archive search and
one or several post languages. Query-translation languages are a separate
multi-select: they create translated variants of each entered search term.

`SEARCH_HANDLES` uses X's `from:` query syntax and therefore applies only to
the X collector. Use ordinary keywords or platform-native handle text when
searching Bluesky and Mastodon.

Start with small post and page limits while confirming that each selected source,
query, credential, and LLM provider works correctly.

## During a run

The script first asks which social-data sources to use. You can select X,
Bluesky, Mastodon, all three, or a comma-separated combination such as `1,2`.
It then asks for search terms and optional languages into which those terms
should be translated. Original terms are always retained; translated variants
are added as extra searches.

API requests and public geocoding can take time. Keep Terminal open until the
script reports the output filenames.

## Troubleshooting

### `externally-managed-environment`

Activate the project virtual environment before running the script:

```bash
source .venv/bin/activate
python3 SUGAR.py
```

### X API authentication or billing error

- `401 Unauthorized`: generate a new App-Only Bearer Token and replace the contents of `.x_bearer_token`.
- `402`: add X API credits or correct the billing configuration.
- `403 Forbidden`: confirm that the app can use recent search.
- `429`: wait for the applicable rate-limit window to reset.

Do not put the Consumer Key or OAuth user Access Token in `.x_bearer_token`.

### LLM authentication error

Run the script again and enter a valid key for the provider you selected. An
OpenAI key and an ARC key are not interchangeable.

### ARC access

ARC's shared API is intended for eligible Virginia Tech users. Generate the key
through your own ARC web profile and keep it confidential.

### No X results

The query may have no matches within the preceding seven days, or date settings
may fall outside the recent-search window. Remove date bounds, broaden the query,
and keep `MAX_POSTS_PER_QUERY` small while testing.

### No Bluesky results

Broaden the query and remove X-specific operators. Bluesky search syntax and
index coverage differ from X, even when the same words are used.

If the error is an HTML `403 Forbidden` response, your network is probably
blocking the public Bluesky API rather than Bluesky rejecting the query. Run
SUGAR again and enter a Bluesky handle plus a dedicated app password when
prompted. Alternatively, try another network or a trusted VPN that allows
`*.bsky.app`. A JSON `401` during login usually means the handle or app password
was entered incorrectly; create a fresh app password and try again.

### No Mastodon results

Try an authenticated user token, select a different Mastodon server relevant to
the community being studied, or use hashtag/account-oriented terms. Full-text
post search is deliberately instance-dependent and is not a universal index.
