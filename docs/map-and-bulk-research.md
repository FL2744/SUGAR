# Map, bulk collection and adaptive website research

The workbench keeps its existing navigation, institution workflows and responsive layout. The map has a larger default canvas, an **Expand map** view (Escape returns to the layout), **Fit visible data**, a metric scale and resize handling when an inspector opens. Institution activity heat uses an unclustered source so it remains visible at regional and world zooms.

## Collection and saved searches

Interpreting a valid search saves its request and plan to the project, including when SUGAR creates the project for that first search. Manual plans and **Save plan** persist before a run is started. Returning to Research or reloading restores the current plan; subsequent edits create versions through the existing backend. An explicit **Save search** action also handles an unsaved preview.

**Edit plan → Bulk collection target** offers 1,000, 5,000 and 10,000 unique items. Each preset sets the total cap, per-query allowance and pagination budget. Advanced limits support up to 10,000 items per query, 100 pages per query and 100,000 items per run. Existing Quick/Standard/Deep defaults are preserved. Source availability and duplicates determine the attainable count; the Results page reports the requested target and actual unique count. A larger collection alone does not establish a representative statistical sample.

The pipeline reserves the shared cap atomically across parallel sources, avoids starting additional queries after the cap is reached, and checkpoints items periodically and when sources finish. Translation retains its existing independent model-call budget. A process interruption preserves the last saved checkpoint; the separate CLI `harvest` workflow remains the durable task-resume interface.

Wikipedia uses MediaWiki search continuation and OpenAlex uses cursor pagination (100 results per page, following the service's [paging documentation](https://help.openalex.org/api/paging/)). Completed pages survive a later request failure. The existing collectors retain their access requirements, rate limits and retry behavior.

## Public sources without new service integrations

Research → **Your own sources** includes additive presets for:

- UN News in English, French, Spanish, Arabic, Chinese and Russian ([UN news outlets](https://www.un.org/de/delegate/page/un-news-outlets)).
- EU Council press releases and foreign-affairs meeting feeds ([official feed directory](https://www.consilium.europa.eu/en/about-site/rss/)).
- UNESCO's public newsroom and EU education, youth, culture and sport meeting feed ([UNESCO newsroom](https://www.unesco.org/en/newsroom)).

The presets populate the existing RSS/web source fields and are saved per project. They require no additional API keys, SDKs or subscriptions. Select RSS/Public web in a selected-source plan, or use All enabled sources. Publisher articles remain labeled by source/content type and should be analyzed separately from social posts. RSS feeds are recent snapshots, not historical archives.

## How website collection adapts without model calls

The website collector now runs a bounded local observe–select–read–reassess loop:

1. Read analyst-provided seeds, respecting the existing public-address checks, robots policy and per-host pacing.
2. Rank same-site links using query words, news/event/program hints and depth. Skip unrelated links, tracking variants, downloads and obvious login/cart paths.
3. Re-rank the frontier as matching pages contribute useful title vocabulary. Default discovery can reach three links beyond a seed.
4. Reuse successful pages across queries within the run. Failed URLs are remembered so a blocked site is not repeatedly fetched.
5. Stop at the item target, an exhausted/irrelevant frontier, diminishing returns (six nonmatching followed pages), a per-query page budget or a hard per-run budget. The default per-query budget is `max(24, pages_per_query × 4)`, capped at 200 page fetches; the run cap is 240. Cooperative pause/cancel is checked before each page.

This loop makes no LLM calls. Existing natural-language planning and translation can still use the provider and budget the analyst chose. There is no unrestricted autonomous web search: discovery stays within the supplied sites and follows observed links. Local lexical relevance cannot replace semantic reading or human source review.

Activity shows each selected page, whether it was cached, its relevance decision and the stop reason. Kept records preserve discovery path, reason, priority, depth, query terms and crawl summary in `source_metadata`, the fetched-document evidence node and machine-readable exports. Run metrics also retain summaries for zero-match searches. The item inspector explains why a website page was collected.

## Time, heat and optional language axes

The map scans all saved runs, including saved partial results, and keeps one accepted observation per stable item identity. It reports unlocated posts separately. Records with invalid legacy coordinates fall back to a text-mentioned place or remain unlocated.

**Posts over time** provides UTC publication-date bounds, a count histogram with empty periods, a time scrubber and cumulative playback. Undated items appear in All time and are excluded from dated views; retrieval time never substitutes for publication time. Targets, flows and visible counts are rebuilt from exactly the visible pins. Sort newest/oldest in both map lists and Results; Results pages make collections of thousands accessible without rendering the entire dataset at once.

Post coloring supports location/review, publication recency and origin density. Density uses recorded origins, excluding places mentioned only in text so country centroids do not become false origin hotspots. Density is relative to the viewport/zoom. Text-mentioned locations and recorded origins remain distinct. Clusters use their latest publication date for recency and the mean of scored items for language axes. Unscored items are gray. Heat and counts do not establish influence.

Enable **Filters and options → exploratory language axes** to show:

- Valence: −1 negative language to +1 positive language.
- Intensity: 0 to 1, based on lexical strength, nearby modifiers and punctuation.
- Direction: −1 self-referential pronouns to +1 other-directed pronouns.

The versioned English lexicon is deterministic and makes no remote calls. English translations are scored only when their target language is explicitly English; the basis is retained. Missing language support or lexical evidence produces null/unscored axes rather than neutral zeros. Every displayed/exported mean has its own scored-item denominator. Negation is approximate; the method is exploratory and is not validated emotion classification or a psychological judgment. Sarcasm, quotation and cultural context require human review.

## Analysis exports

Run bundles retain their original files and add `analysis.csv`, `analysis.jsonl`, `timeline.csv`, `map.geojson`, `data-dictionary.json` and `README-analysis.md`. **Export mapped posts** exports the active date/review/rolling-window scope across all runs; a target's inspector can restrict it to posts mentioning that target. Map exports include mapped posts only, as recorded in their manifest.

The analysis table preserves the full ingested text (rather than map preview snippets), stable join keys, publication/retrieval times, query provenance, review decisions, original versus translated text, engagement, qualified locations and optional language axes. CSV uses UTF-8 BOM, RFC 4180 quoting and spreadsheet-formula protection; JSONL preserves exact strings and structured values. Daily timeline rows separate source/language and include a nonmissing denominator for each axis. GeoJSON uses WGS84 longitude/latitude and explicitly labels origin versus approximate text placement. Dictionaries document nulls, units, sampling limits and loading in pandas, R and QGIS. All added files are included in the existing SHA-256 manifest and verification path.
