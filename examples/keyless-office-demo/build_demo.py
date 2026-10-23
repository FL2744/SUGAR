"""Build a clearly synthetic Americas office-workflow demo without network calls.

Run from the repository root: python examples/keyless-office-demo/build_demo.py
The output is a new temporary workspace, never an existing research project.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sugar_core.activity_coding import code_items
from sugar_core.evidence_desk import export_package
from sugar_core.institutions import promote
from sugar_core.mission_rubric import load_rubric, save_rubric
from sugar_core.monitoring import build_digest
from sugar_core.networks import set_network
from sugar_core.reference_registry import upsert_entity
from sugar_core.research_items import ResearchItem, tag_geography
from sugar_core.research_plan import ResearchPlanSpec
from sugar_core.research_runs import ResearchProject
from sugar_core.workspace import SugarWorkspace


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="sugar-office-demo-")) / "project"
    p = ResearchProject(SugarWorkspace.create(root, name="SYNTHETIC DEMO · Mexico office workflow"))
    run = p.new_run(plan=ResearchPlanSpec(research_question="Synthetic demonstration of a credential-free office workflow"))
    rubric = load_rubric(p)
    rubric["alert_terms"] = ["example narrative review phrase"]
    save_rubric(p, rubric)
    set_network(p, "Synthetic subject network", role="subject")
    set_network(p, "Synthetic reference locations", role="reference")
    now = datetime.now(timezone.utc)
    examples = [
        ("Synthetic Harbor Institute", "Merida", 20.97, -89.59, now - timedelta(days=10), "Commercial diplomacy workshop for engineers and business leaders. Attendance: 120 participants. An example narrative review phrase for demonstration only."),
        ("Synthetic River Institute", "Mexico City", 19.43, -99.13, now - timedelta(days=25), "Teacher training and scholarship course registration for university students."),
        ("Synthetic Historic Institute", "Monterrey", 25.69, -100.32, datetime(2023, 5, 1, tzinfo=timezone.utc), "A tea ceremony and cultural festival in 2023."),
        ("Synthetic Closure Review Institute", "Tijuana", 32.51, -117.04, now - timedelta(days=5), "El Instituto Confucio cerró sus puertas. Cursos cancelados definitivamente."),
    ]
    items = []
    for n, (name, city, lat, lon, date, text) in enumerate(examples, 1):
        url = f"https://example.org/synthetic-demo/{n}/event"
        post = ResearchItem(item_id=f"it_demo_{n}", run_id=run.run_id, project_id=p.project_id, platform="web", url=url,
                            published_at=date.isoformat(), retrieved_at=now.isoformat(), language="en", original_text="SYNTHETIC DEMONSTRATION. Mexico. " + text,
                            status="processed", source_metadata={"synthetic": True, "event_dates": [date.date().isoformat()] if n <= 2 else []})
        tag_geography(post, [])
        items.append(post)
    p.save_items(run.run_id, items)
    build_digest(p, trigger="demo_baseline")
    for (name, city, lat, lon, _, _), post in zip(examples, items):
        promote(p, {"name": name, "network": "Synthetic subject network", "country": "Mexico", "city": city, "latitude": lat, "longitude": lon,
                    "location_precision": "city", "public_links": [post.url.rsplit("/", 1)[0]]}, [(post, "")], actor="synthetic demo")
    for name, lat, lon in [("Synthetic American Space", 20.99, -89.62), ("Synthetic Embassy", 19.42, -99.15)]:
        upsert_entity(p.workspace, {"name": name, "country": "Mexico", "latitude": lat, "longitude": lon, "network": "Synthetic reference locations"},
                      evidence_refs=[{"source_url": "https://example.org/synthetic-demo/reference", "note": "Invented demonstration location"}])
    code_items(p, items)
    run.status, run.finished_at = "completed", now.isoformat()
    run.counts = {"collected": len(items), "processed": len(items)}
    p.save_run(run)
    build_digest(p, run_id=run.run_id, trigger="demo", items=items)
    exported = export_package(p, country="Mexico")
    print(root / exported["directory"] / "country-snapshot.html")
    print(root / exported["archive"])


if __name__ == "__main__":
    main()
