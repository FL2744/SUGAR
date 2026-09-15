# Kyrgyzstan 2026 end-to-end case

This directory is a reproducible, public-source exercise that runs a bounded Kyrgyzstan research case through SUGAR's current workspace, observation, State-assessment, audit, mapping, U.S.-presence comparison, source-conflict, review, and briefing gates.

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

That mix forces SUGAR to distinguish physical proximity from service availability, preserve location and reach uncertainty, support multi-site activity without double-counting, and carry contradictory source claims into analyst review instead of silently resolving them.

## Evidence and review status

The case contains **11 real public-source PRC-linked observations**. Sources include the PRC Embassy in Kyrgyzstan, Osh State University, Kyrgyz National University, and Kyrgyz national news agency Kabar.

All observations and State assessments are intentionally marked **`ai_triaged`**, not `human_verified`. The purpose is to test SUGAR's actual review gate:

- the analyst/research map may display AI-triaged records for review;
- the verified-only State map must not display those PRC observations;
- the State briefing package must not promote AI-triaged material into human-verified judgments.

Do not change those review states merely to make the example brief look fuller. A human analyst should review the source evidence first.

The case now reports two separate audit concepts:

- **record-integrity audit: `pass`** — the observation/assessment records satisfy SUGAR's evidence and verification integrity rules;
- **complete State-package audit: `conditional`** — the package carries a real, unresolved EducationUSA service-topology source conflict that still requires human review.

A conditional package is not a failed dataset. It means the contradiction is preserved and visible rather than hidden.

## Location precision workflow

The first execution of this case exposed an important realism problem: using the same Bishkek city centroid for both PRC activities and the Bishkek American Space made multiple center-to-center distances equal to `0.0 km`. The uncertainty model prevented a literal same-building claim, but the geometry was still too coarse to be useful.

The case therefore keeps source coding separate from a deterministic location-enrichment stage:

- **7 single-site observations** are refined to site-level geometry with separate public location references;
- **3 single-site observations** remain deliberately city-level because their public sources are city-wide or venue-ambiguous;
- **1 International Chinese Language Day observation** remains one logical activity while carrying **2 structured activity locations**;
- Bishkek State University is represented at site precision for that multi-site record;
- International University of Kyrgyzstan remains at city precision because the public evidence does not resolve which current campus hosted the activity;
- the analyst map therefore contains **12 activity locations for 11 observations**, while the density layer still totals exactly **11.0 activity units**;
- America Borboru Bishkek and American Corner Osh are address-refined from the official American Spaces locator plus public coordinate references;
- the other six physical American Spaces remain explicitly labeled city-centroid references until stronger current site coordinates are independently supported.

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
- `references/source_conflicts.json`
- `references/us_presence.csv`
- `state/kyrgyzstan_2026.state.jsonl`
- `state/kyrgyzstan_2026.source_conflicts.json`
- `state/kyrgyzstan_2026.review_queue.csv`
- `state/kyrgyzstan_2026.state.xlsx`
- `state/kyrgyzstan_2026.audit.json`
- `state/kyrgyzstan_2026.brief.md`
- the rest of the normal State package under `state/`
- `outputs/maps/kyrgyzstan_2026.analyst.html`
- `outputs/maps/kyrgyzstan_2026.verified.html`
- map metadata ledgers for both maps
- `outputs/reports/case-summary.json`
- `outputs/reports/case-findings.json`
- `outputs/reports/case-audit.json`
- `outputs/reports/record-integrity-audit.json`
- `outputs/reports/preliminary-analyst-note.md`

CI runs this case and uploads the complete workspace as an artifact so the outputs can be inspected without relying on a developer's local environment.

## U.S. comparison layer

The current American Spaces locator lists eight physical Spaces in Kyrgyzstan: Bishkek, Jalal-Abad, Talas, Batken, Kant, Karakol, Naryn, and Osh.

The official locator provides current street addresses for America Borboru Bishkek and American Corner Osh, so the case refines those two reference points to site/address precision with a **0.25 km** uncertainty value. The remaining six Spaces use explicitly labeled city-centroid references with a **12 km** uncertainty value. `USPresenceSite` stores precision, confidence, basis, and uncertainty per record, so the map no longer needs one blanket uncertainty value for mixed-quality U.S. locations.

EducationUSA Kyrgyzstan is represented as a **virtual, country-scoped service** because the current official EducationUSA directory says advising services became fully online on April 1, 2026 and lists `No physical Address`. It can therefore contribute higher-education service availability without becoming a map point or replacing the nearest physical American Space.

The current American Councils Kyrgyzstan program page still describes an advising center at the Bayalinov Youth and Children's Library / American Corner in Bishkek. SUGAR preserves that contradiction as a first-class `SourceConflict` with both source claims, authority/freshness metadata, the provisional current treatment, and a human-review requirement. The State package carries that conflict into its JSON, audit, review queue, workbook, snapshot, and BLUF. Only records whose structured higher-education service analysis actually depends on the EducationUSA source inherit the conflict review flag; audience similarity alone does not spread it to unrelated records.

The current treatment is operational, not a human adjudication and not proof that either public page is fabricated.

## Real-case stress tests now resolved in the model

The case originally exposed several schema/workflow failures. They now serve as permanent regressions rather than open architecture gaps:

1. **Generic language education — resolved.** Chinese-language activity uses the language-neutral `language_education` domain instead of falling into `other` or being equated with English-language programming.
2. **Direct service vs audience overlap — resolved.** A shared student audience does not manufacture an English-language or EducationUSA service equivalence; audience, thematic, and direct service overlap remain separate dimensions.
3. **Virtual national services — resolved.** Country-scoped virtual EducationUSA service availability is evaluated independently of nearest physical-site geography and remains non-spatial.
4. **Per-site U.S. location precision — resolved.** Physical U.S. presence records carry their own precision, confidence, provenance, and uncertainty values.
5. **Qualified reach metrics — resolved.** `roughly 300`, `roughly 200`, and `more than 1,000` remain structured approximate/minimum values with source provenance and do not leak into fabricated exact totals.
6. **Multi-site observations — resolved.** One logical activity can carry multiple independently sourced locations while contributing only one total activity unit to density/counting.
7. **Structured U.S. service provenance — resolved.** Overlap assessments preserve which U.S. service records contributed, with program-service matches separated from audience-associated matches.
8. **Source conflicts — resolved as a workflow capability.** Contradictory reference records are first-class objects and travel through normal State package/review surfaces instead of living only in a case-specific side file.

## Remaining case limitations and review work

These are deliberately not papered over:

- **Human verification remains outstanding.** All 11 PRC-linked observations and assessments are still AI-triaged, so verified-only State outputs remain empty by design.
- **EducationUSA topology still requires analyst adjudication.** SUGAR preserves the contradiction and uses the current State directory provisionally, but the system does not claim the conflict is finally resolved.
- **Six physical American Spaces remain city-centroid references.** Their uncertainty is represented honestly; they can be refined if stronger current public location evidence is found.
- **One International University of Kyrgyzstan venue remains campus-ambiguous.** The multi-site schema preserves the activity without guessing which campus hosted it.

These are evidence/review limitations, not reasons to weaken the model guardrails.

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

This case identifies observable activity, coded audiences/themes, evidence status, and geographic/service relationships. It does **not** infer that PRC programming displaced U.S. programming, changed attitudes, caused behavior, or produced strategic influence. Geographic proximity, thematic similarity, service availability, and reported reach are research leads or descriptive attributes, not causal findings.