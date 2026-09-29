# Ghana education and cultural-program research demo

This compact SUGAR project is a meeting-ready example of a source-backed institutional research workflow. It includes an imported institution registry, explicit relationship evidence, a populated map, an initial saved search plan and project history, documented evidence gaps, and a portable handoff bundle.

The underlying SUGAR capabilities are part of the 1.3 product. This directory supplies example research content; it does not claim to be an authoritative or complete inventory.

## Open the prepared project

Open [`workspace/sugar-project.json`](workspace/sugar-project.json) in SUGAR, or run:

```powershell
python -c "from sugar_core.workspace_cli import main; main()" status examples/ghana-education-research/workspace
```

The prepared project includes:

- three EducationUSA centers in Accra and Kumasi;
- historical American Spaces references in Accra, with current status left unknown;
- the University of Ghana campus, its Confucius Institute, and the source-backed CIUG–Zhejiang University of Technology relationship;
- source-specific claims and eight registry relationships;
- city/campus-level map points with OpenStreetMap provenance;
- a research requirement, initial search plan, and project event history;
- canonical source records, research observations, an evidence-gaps note, and an exported ZIP handoff.

Open the map at [`workspace/outputs/maps/ghana-education-research.html`](workspace/outputs/maps/ghana-education-research.html). The map uses a web basemap; the interactive map needs internet access to load its map tiles and JavaScript libraries.

The exported handoff is [`ghana-education-research.zip`](workspace/outputs/exports/handoff/ghana-education-research.zip). Its extracted directory sits beside the ZIP and includes the requirement, search plan, evidence records, observations, lineage, limitations, source registry, and map.

## Rebuild in a clean location

From the SUGAR repository root, create a fresh project from the checked-in inventory:

```powershell
python examples/ghana-education-research/build_demo.py --output "$env:TEMP/ghana-education-research-demo"
```

Use a fresh output directory. The builder previews the source table, imports the mapped fields as unreviewed claims, adds separately sourced approximate location claims, builds the map through the workspace hub, and exports a ZIP handoff. It performs no online collection or geocoding.

To reproduce the import preview on its own:

```powershell
python -c "from sugar_core.workspace_cli import main; main()" registry-preview examples/ghana-education-research/source-inventory.csv
```

## Two-minute walkthrough

1. Open the prepared project and show its dashboard and `project-history`.
2. Open `research-requirement.json` and `search-plan.json` to show the requirement translated into bounded, editable query branches.
3. Inspect the registry and its evidence-backed `member_of`, `hosted_by`, and `partner_of` relationships.
4. Open the map, select the Accra cluster, and point out that its location precision is city-level. Compare with the University of Ghana campus-level points.
5. Open `evidence-gaps.md` and the exported handoff ZIP to show which details remain unresolved and what another analyst receives.

The project preserves uncertainty instead of presenting unknown status as closure or an approximate map point as an exact address. It makes no claims about influence, outcomes, or complete national coverage.
