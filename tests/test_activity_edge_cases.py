import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from sugar_core.evidence_desk import capture_pages, country_snapshot, export_package
from sugar_core.mission_rubric import classify_text, load_rubric
from sugar_core.networks import import_upload, preview_upload
from sugar_core.reference_registry import import_status, import_status_confidence, list_entities
from sugar_core.research_plan import ResearchPlanSpec
from sugar_core.temporal import rolling_year_start
from sugar_core.web_sources import extract_page
from test_evidence_desk import NOW, entity, item, project


def assessment(text, *, date="2026-10-01", now=NOW, metadata=None):
    post = item(text, date=date, source_metadata=metadata or {})
    return assess_items([post], now=now)


def assess_items(posts, *, now=NOW):
    from sugar_core.institution_activity import assess
    return assess(entity(), [{"item_id": p.item_id} for p in posts], {p.item_id: p for p in posts}, now=now)


@pytest.mark.parametrize("phrase", [
    "El Instituto Confucio cerró sus puertas. Cursos cancelados definitivamente.",
    "Cierre del centro y cancelación de cursos.", "Os cursos foram encerrados.",
    "Fermeture du centre. Les cours sont annulés.", "The institute shut down; courses terminated.",
    "Permanent closures announced; workshops discontinued.", "学校课程取消。", "O centro foi fechado.",
])
def test_multilingual_closure_never_proves_active_programming(phrase):
    result = assessment(phrase)
    assert result["status"] == "unknown" and result["needs_review"]
    assert result["signals"][0]["negative_cue"] and not result["last_activity_date"]


def test_negative_evidence_still_flags_review_alongside_current_programs():
    positive = item("Registration open for Autumn 2026 courses.")
    negative = item("Cierre del centro.")
    negative.item_id = "it_negative"
    result = assess_items([positive, negative])
    assert result["label"] == "Active, high confidence" and result["needs_review"]


@pytest.mark.parametrize("text", [
    "Inicio | Cursos | Eventos | Contacto. El instituto fue fundado en 2004.",
    "Home | Courses | Events | Contact. Founded in 2004.",
    "Cours | Événements | Contact. L'institut a été fondé en 2004.",
    "The institute offers courses and workshops. Contact our staff.",
])
def test_navigation_and_undated_program_nouns_are_presence_only(text):
    result = assessment(text)
    assert result["label"] == "Active, medium confidence"
    assert not result["signals"][0]["program"] and not result["last_activity_date"]


@pytest.mark.parametrize("text,metadata", [
    ("Our institute welcomes you.", {"event_dates": ["2026-11-01"]}),
    ("Courses begin in Autumn 2026.", {}), ("Registration is now open for courses.", {}),
    ("A workshop was held on 10 October.", {}),
    ("Inscripción abierta para cursos.", {}), ("Les inscriptions sont ouvertes pour les cours.", {}),
])
def test_explicit_program_context_is_required_and_sufficient(text, metadata):
    assert assessment(text, metadata=metadata)["label"] == "Active, high confidence"


def test_rolling_window_crosses_new_year_without_downgrading_dated_evidence():
    text = "Registration open for Autumn 2026 courses."
    for now in (datetime(2026, 12, 30, tzinfo=timezone.utc), datetime(2027, 1, 5, tzinfo=timezone.utc)):
        result = assessment(text, now=now)
        assert result["label"] == "Active, high confidence"
        assert not result["needs_review"]
    prior_term = assessment(text, date="", now=datetime(2027, 1, 5, tzinfo=timezone.utc))
    assert prior_term["label"] == "Active, medium confidence" and not prior_term["needs_review"]
    republished = assessment(text, date="2027-01-02", now=datetime(2027, 1, 5, tzinfo=timezone.utc))
    assert republished["label"] == "Active, medium confidence"
    stale = assessment("Registration for Autumn 2024 courses.", now=datetime(2027, 1, 5, tzinfo=timezone.utc))
    assert stale["status"] == "unknown" and stale["needs_review"]
    assert rolling_year_start(datetime(2028, 2, 29)) == "2027-02-28"


@pytest.mark.parametrize("label,status,confidence", [
    ("Active — High confidence", "active", "high"), ("Active – Medium confidence", "active", "medium"),
    ("Active - High confidence", "active", "high"), ("Active (High)", "active", "high"),
    ("Active, medium confidence", "active", "medium"), ("Restructured", "renamed", ""),
    ("Renamed / restructured", "renamed", ""), ("Status unclear", "unknown", ""),
])
def test_group_status_wording_is_normalized_without_losing_reported_confidence(tmp_path, label, status, confidence):
    assert import_status(label) == status and import_status_confidence(label) == confidence
    p = project(tmp_path)
    source = io.StringIO()
    writer = csv.writer(source)
    writer.writerow(["name", "country", "status", "source_url"])
    writer.writerow(["Harbor Institute", "Mexico", label, "https://example.org/registry"])
    preview = preview_upload(p, "status.csv", source.getvalue().encode())
    assert not preview["error_count"]
    import_upload(p, preview["file_id"], mapping=preview["suggested_mapping"], network="subject", role="subject")
    row = list_entities(p.workspace)[0]
    assert row["status"] == status and row["reported_status_confidence"] == confidence
    refs = [ref for claim in row["claims"] for ref in claim["evidence_refs"]]
    assert any(ref["reported_status"] == label and ref.get("reported_status_confidence", "") == confidence for ref in refs)
    assert all(c["review_state"] != "human_verified" for c in row["claims"])


@pytest.mark.parametrize("text,tier", [
    ("鲁班工坊人工智能培训班开班", "A"), ("Luban Workshop trains engineers in 5G and new energy vehicles", "A"),
    ("Taller de inteligencia artificial para ingenieros mineros", "A"), ("Belt and Road digital economy forum", "A"),
    ("Formação em inteligência artificial e mineração", "A"), ("Atelier d'intelligence artificielle", "A"),
    ("职业教育培训班", "B"), ("Luban Workshop vocational training", "B"), ("一带一路合作论坛", "B"),
    ("Formation professionnelle pour jeunes dirigeants", "B"), ("Chinese Bridge competition", "C"),
    ("教师培训", "C"), ("Ceremonia del té", "D"), ("Freedom 250", "A"),
])
def test_default_tiers_match_program_sectors_across_languages(tmp_path, text, tier):
    rules = load_rubric(project(tmp_path))
    assert [c["label"] for c in classify_text(text, rules) if c["field"] == "priority_tier"] == [tier]


@pytest.mark.parametrize("date_html,basis", [
    ('<time datetime="2026-10-01T08:00:00Z">October 1</time>', "time:datetime"),
    ('<script type="application/ld+json">{"@graph":[{"@type":"SocialMediaPosting","datePublished":"2026-10-01T08:00:00Z","text":"not retained"}]}</script>', "jsonld:datePublished"),
    ('<meta property="article:published_time" content="2026-10-01T08:00:00Z">', "meta:article:published_time"),
    ('<script type="application/ld+json">{"dateModified":"2026-10-01T08:00:00Z"}</script>', "undated"),
])
def test_saved_pages_share_publication_extraction_without_retaining_scripts(tmp_path, date_html, basis):
    p = project(tmp_path)
    html = '<html>' + date_html + '<p>Registration open for courses.</p><script>private-script</script></html>'
    result = capture_pages(p, [{"filename": "social.html", "source_url": "https://institute.example/programs/post", "html": html}])
    post = p.load_items(result["run_id"])[0]
    assert post.source_metadata["published_basis"] == basis
    assert bool(post.published_at) == (basis != "undated")
    assert extract_page(html)["published"] == post.published_at
    assert "not retained" not in post.original_text and "private-script" not in post.original_text
    assert assess_items([post])["confidence"] == ("high" if post.published_at else "low")


def test_ai_export_requires_scope_and_country_packages_exclude_other_countries(tmp_path):
    p = project(tmp_path)
    run = p.new_run(plan=ResearchPlanSpec(research_question="Country export scope"))
    posts = [item("Courses in Mexico"), item("Courses in France")]
    for post, name in zip(posts, ["Mexico", "France"]):
        post.item_id = name
        post.run_id = run.run_id
        post.geography = [{"name": name, "method": "text_match"}]
    p.save_items(run.run_id, posts)
    with pytest.raises(ValueError, match="Choose a country"):
        export_package(p, ai_only=True)
    for country, all_countries, expected in [("Mexico", False, {"Mexico"}), ("France", False, {"France"}), ("", True, {"Mexico", "France"})]:
        result = export_package(p, country=country, ai_only=True, all_countries=all_countries)
        with zipfile.ZipFile(p.workspace.root / result["archive"]) as archive:
            content = archive.read(next(n for n in archive.namelist() if n.endswith("evidence-package.jsonl")))
            assert {json.loads(line)["item_id"] for line in content.splitlines()} == expected
            manifest = json.loads(archive.read(next(n for n in archive.namelist() if n.endswith("run-manifest.json"))))
            assert manifest["scope"]["country"] == country


def test_old_capture_cache_can_be_reprocessed_for_new_publication_dates(tmp_path):
    p = project(tmp_path)
    page = {"filename": "social.html", "source_url": "https://institute.example/programs/social", "html": '<time datetime="2026-10-01">October 1</time><p>Registration open for courses.</p>'}
    first = capture_pages(p, [page])
    legacy = p.load_items(first["run_id"])[0]
    legacy.published_at = ""
    p.save_items(first["run_id"], [legacy])
    old_hash = hashlib.sha256((page["source_url"] + "\n" + page["html"]).encode()).hexdigest()
    (p.root / "capture-inputs.json").write_text(json.dumps({old_hash: legacy.item_id}))
    updated = capture_pages(p, [page])
    assert updated["imported"] == 1
    post = p.load_items(updated["run_id"])[0]
    assert post.item_id == legacy.item_id and post.published_at.startswith("2026-10-01")
    assert not p.load_items(first["run_id"])[0].published_at
    from sugar_core.evidence_desk import all_items
    assert len(all_items(p)) == 1


def test_country_snapshot_and_activity_share_the_rolling_window(tmp_path):
    p = project(tmp_path)
    run = p.new_run(plan=ResearchPlanSpec(research_question="Rolling current window"))
    post = item("Registration open for Autumn 2026 courses.")
    post.run_id = run.run_id
    p.save_items(run.run_id, [post])
    from sugar_core.reference_registry import upsert_entity
    upsert_entity(p.workspace, {"name": "Harbor", "country": "Mexico", "public_links": ["https://institute.example/programs"]}, evidence_refs=[{"source_url": "https://institute.example/programs"}])
    with patch("sugar_core.institution_activity.datetime") as activity_clock, patch("sugar_core.evidence_desk.datetime") as snapshot_clock:
        activity_clock.now.return_value = snapshot_clock.now.return_value = datetime(2027, 1, 5, tzinfo=timezone.utc)
        snapshot = country_snapshot(p, "Mexico")
    assert snapshot["institutions"][0]["activity_assessment"]["label"] == "Active, high confidence"
    assert snapshot["recent_programs"][0]["item_id"] == post.item_id
