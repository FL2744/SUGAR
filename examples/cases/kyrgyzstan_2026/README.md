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
- EducationUSA Kyrgyzstan operating as a fully online service beginning April 1, 2026.

That mix forces SUGAR to distinguish physical proximity from service overlap and to represent evidence precision instead of treating every public-diplomacy activity as the same kind of object.

## Evidence and review status

The case contains **11 real public-source PRC-linked observations**. Sources include the PRC Embassy in Kyrgyzstan, Osh State University, Kyrgyz National University, and Kyrgyz national news agency Kabar.

All observations and State assessments are intentionally marked **`ai_triaged`**, not `human_verified`. The purpose is to test SUGAR's actual review gate:

- the analyst/research map may display AI-triaged records for review;
- the verified-only State map must not display those PRC observations;
- the State briefing package must not promote AI-triaged material into human-verified judgments.

Do not change those review states merely to make the example brief look fuller. A human analyst should review the source evidence first.

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

For reproducibility, this case uses city-centroid coordinates for those physical Spaces rather than pretending that every current building coordinate has been independently verified. The map therefore receives a conservative **12 km U.S.-site uncertainty envelope**. This is deliberately less precise than a building-level point.

EducationUSA Kyrgyzstan is represented without coordinates because its official EducationUSA page states that advising became fully online beginning April 1, 2026. A virtual national service should not be placed at a fake physical point.

## Current model gaps exposed by the case

The case is designed to record real friction instead of hiding it. Its generated `case-findings.json` currently checks for four important modeling gaps:

1. **Generic language education.** The State domain taxonomy has `english_language` but no generic `language_education`, forcing Chinese-language activity into `other` even though language education is central to the case.
2. **Virtual national services.** The existing U.S.-overlap model derives service overlap from the nearest physical site and therefore does not naturally aggregate a nationally available virtual EducationUSA service.
3. **Per-site location precision.** U.S. presence records do not yet carry their own precision/confidence/uncertainty fields, so this case has to provide one conservative uncertainty assumption for the physical U.S. layer.
4. **Qualified reach metrics.** Public sources frequently say `about 300`, `hundreds`, or `more than 1,000`. Current `ReachMetrics` stores bare integers, so the case refuses to turn those statements into false exact totals.

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
- EducationUSA Advising Center, Kyrgyzstan: https://educationusa.state.gov/node/421

## Analytic guardrail

This case identifies observable activity, coded audiences/themes, evidence status, and geographic/service relationships. It does **not** infer that PRC programming displaced U.S. programming, changed attitudes, caused behavior, or produced strategic influence. Geographic proximity and thematic similarity are research leads, not causal findings.
