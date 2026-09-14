# Kyrgyzstan 2026 end-to-end case

This directory is a reproducible, public-source exercise that runs a bounded Kyrgyzstan research case through SUGAR's current workspace, observation, State-assessment, audit, mapping, U.S.-presence comparison, and briefing gates.

The research cutoff is **September 14, 2026**.

## Why this case

Kyrgyzstan is a useful stress test because the 2026 public-diplomacy landscape includes several distinct PRC engagement modes at once:

- Confucius Institute and Chinese-language education;
- university partnerships and teaching materials;
- Chinese cultural exhibitions, performances, and public events;
- literary and subnational/city exchange;
- governance and civilizational-dialogue programming;
- a physical U.S. American Spaces network distributed across the country; and
- EducationUSA Kyrgyzstan, whose current official State directory describes a fully online advising service beginning April 1, 2026.

That mix forces SUGAR to distinguish physical proximity from service overlap and to represent evidence precision instead of treating every public-diplomacy activity as the same kind of object.

## Evidence and review status

The case contains **11 real public-source PRC-linked observations**. Sources include the PRC Embassy in Kyrgyzstan, Osh State University, Kyrgyz National University, and Kyrgyz national news agency Kabar.

All observations and State assessments are intentionally marked **`ai_triaged`**, not `human_verified`. The purpose is to test SUGAR's actual review gate:

- the analyst/research map may display AI-triaged records for review;
- the verified-only State map must not display those PRC observations;
- the State briefing package must not promote AI-triaged material into human-verified judgments.

Do not change those review states merely to make the example brief look fuller. A human analyst should review the source evidence first.

## Location precision workflow

The first execution of this case exposed an important realism problem: using the same Bishkek city centroid for both PRC activities and the Bishkek American Space made multiple center-to-center distances equal to `0.0 km`. The uncertainty model prevented a literal same-building claim, but the geometry was still too coarse to be useful.

The case therefore keeps the initial source coding separate from a deterministic location-enrichment stage:

- **7 observations** name a venue or institution clearly enough to refine to site-level coordinates with a separate public location reference;
- **4 observations** remain deliberately city-level because the public source is city-wide, venue-ambiguous, or describes activity at multiple sites;
- the multi-university International Chinese Language Day record is intentionally *not* collapsed onto one university;
- America Borboru Bishkek and American Corner Osh are address-refined from the official American Spaces locator plus public coordinate references;
- the other six physical American Spaces remain city-centroid references until their current site coordinates are independently verified.

The generated `references/location_references.json` preserves those coordinate sources and notes. Location references refine *where* a source-named venue sits; they do not add evidence that the event itself occurred there beyond the underlying activity source.

## Run it

From the repository root:

```bash
python examples/cases/kyrgyzstan_2026/run_case.py \
  --output /tmp/sugar-kyrgyzstan-2026 \
  --clean
```

The output is a normal SUGAR project workspace with the standard portable layout.

Key outputs include:

- `data/observations/kyrgyzstan_2026.observations.csv`
- `references/sources.json`
- `references/location_references.json`
- `references/us_presence.csv`
- `state/kyrgyzstan_2026.state.jsonl`
- the normal State package under `state/`
- `outputs/maps/kyrgyzstan_2026.analyst.html`
- `outputs/maps/kyrgyzstan_2026.verified.html`
- map metadata ledgers for both maps
- `outputs/reports/case-summary.json`
- `outputs/reports/case-findings.json`
- `outputs/reports/case-audit.json`
- `outputs/reports/preliminary-analyst-note.md`

CI runs this case and uploads the complete workspace as an artifact so the outputs can be inspected without relying on a developer's local environment.

## U.S. comparison layer

The current American Spaces locator lists eight physical Spaces in Kyrgyzstan: Bishkek, Jalal-Abad, Talas, Batken, Kant, Karakol, Naryn, and Osh.

The official locator provides current street addresses for America Borboru Bishkek and American Corner Osh, so the case refines those two reference points to their building areas. The remaining six Spaces continue to use city centroids. Because `USPresenceSite` cannot yet store different precision and uncertainty for individual sites, the map still receives a conservative **12 km U.S.-site uncertainty envelope for every physical site**. That deliberately overstates uncertainty for the two address-refined sites rather than overstating precision for the six city-centroid sites.

EducationUSA Kyrgyzstan is represented without coordinates because the current official EducationUSA directory says advising services became fully online on April 1, 2026 and lists `No physical Address`. However, the current American Councils Kyrgyzstan program page still describes an advising center at the Bayalinov Youth and Children's Library / American Corner in Bishkek. The case treats the Department of State directory as the current service-topology authority while preserving this contradiction as a **source-freshness conflict that requires analyst awareness**, not as proof that either page is fabricated.

## Current model gaps exposed by the case

The case is designed to record real friction instead of hiding it. Its generated findings cover these important modeling gaps:

1. **Generic language education.** The State domain taxonomy has `english_language` but no generic `language_education`, forcing Chinese-language activity into `other` even though language education is central to the case.
2. **Virtual national services.** The existing U.S.-overlap model derives service overlap from the nearest physical site and therefore does not naturally aggregate a nationally available virtual EducationUSA service.
3. **Per-site location precision.** U.S. presence records do not yet carry their own precision/confidence/provenance/uncertainty fields, so a mixed exact/centroid reference layer still requires one blanket uncertainty value.
4. **Qualified reach metrics.** Public sources frequently say `about 300`, `hundreds`, or `more than 1,000`. Current `ReachMetrics` stores bare integers, so the case refuses to turn those statements into false exact totals.
5. **Multi-site observations.** One source can report activity at several venues, but `ResearchObservation` currently carries one location. The case leaves the two-university Language Day record at city precision rather than inventing a canonical venue.
6. **Source freshness/conflict.** Official State and implementing-partner pages can disagree about current service topology. SUGAR needs a first-class way to preserve and adjudicate contradictory reference records rather than silently selecting one.

Those are product findings, not reasons to weaken the evidence gate.

## Primary public sources

PRC-linked observations:

- Chinese painting exhibition, March 10: https://kg.china-embassy.gov.cn/dssghd/202603/t20260312_11873181.htm
- Osh State University Confucius Institute cooperation, April 13: https://www.oshsu.kg/public/en/news/4245
- Chinese-language teaching materials, April 15: https://kg.china-embassy.gov.cn/rus/dssghd/202604/t20260417_11893762.htm
- International Chinese Language Day, April 24: https://kg.china-embassy.gov.cn/chn/dssghd/202604/t20260424_11899331.htm
- Chinese Bridge qualifier, May 14: https://www.knu.kg/ky/en/archives/3184
- Diplomatic charity bazaar cultural programming, June 13: https://kg.china-embassy.gov.cn/chn/dssghd/202606/t20260614_11944379.htm
- Writers organizations agreement, June 17: https://en.kabar.kg/news/writers-from-kyrgyzstan-and-china-signed-cooperation-agreement/
- `The Governance of China` presentation, July 14: https://en.kabar.kg/news/presentation-of-xi-jinpings-book-the-governance-of-chinaheld-in-bishkek/
- SCO Civilizations Dialogue, July 14: https://kg.china-embassy.gov.cn/zjsbwl/202607/t20260715_11982757.htm
- `Manas` dance drama premiere, August 21: https://kg.china-embassy.gov.cn/dssghd/202608/t20260822_12008606.htm
- Nanjing Week, August 26: https://en.kabar.kg/news/nanjing-week-in-bishkek-opens-platform-for-cultural-and-literary-exchange/

U.S. comparison references:

- American Spaces locator, Kyrgyzstan: https://americanspaces.info/locator/spaces/KG
- America Borboru Bishkek: https://americanspaces.info/locator/acamericaborborubishkek
- American Corner Osh: https://americanspaces.info/locator/acosh
- EducationUSA Advising Center, Kyrgyzstan: https://educationusa.state.gov/node/421
- American Councils Kyrgyzstan EducationUSA page: https://kyrgyzstan.americancouncils.org/edusa

## Analytic guardrail

This case identifies observable activity, coded audiences/themes, evidence status, and geographic/service relationships. It does **not** infer that PRC programming displaced U.S. programming, changed attitudes, caused behavior, or produced strategic influence. Geographic proximity and thematic similarity are research leads, not causal findings.
