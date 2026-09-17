from __future__ import annotations

import json
from pathlib import Path

from sugar_core.models import PostRecord, merge_record
from sugar_core.observations import EvidenceReference, ResearchObservation

FIXTURE = Path(__file__).parent / "fixtures" / "evidence_nasty.json"


def test_adversarial_evidence_corpus_preserves_source_edge_cases() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["schema_version"] == 1
    cases = {item["kind"]: item for item in fixture["cases"]}

    deleted = PostRecord(**cases["deleted"]["record"])
    assert deleted.record_key == cases["deleted"]["expect"]["record_key"]
    assert deleted.raw_stats["availability"] == cases["deleted"]["expect"]["availability"]
    assert not deleted.original_text

    before = PostRecord(**cases["edited"]["before"])
    after = PostRecord(**cases["edited"]["after"])
    assert before.record_key == after.record_key
    assert before.original_text != after.original_text
    merge_record(before, after)
    assert before.record_key == after.record_key
    assert before.query_matches == ["students", "education"]
    assert before.engagement == {"likes": cases["edited"]["expect"]["latest_likes"]}

    repost = PostRecord(**cases["reposted"]["record"])
    assert repost.is_repost is cases["reposted"]["expect"]["is_repost"]
    assert repost.raw_stats["reblog_id"] == cases["reposted"]["expect"]["origin_id"]

    contradictory = ResearchObservation(**cases["contradictory"]["observation"])
    contradictory.transition_verification("human_verified", reviewer="Analyst A", notes="First source reviewed.")
    contradictory.transition_verification(
        "needs_followup", reviewer="Analyst B", notes="Second source contradicts the reviewed claim."
    )
    assert contradictory.verification_state == cases["contradictory"]["expect"]["final_state"]
    assert (
        contradictory.provenance[0].conflict_history[0]["event"] == cases["contradictory"]["expect"]["conflict_event"]
    )

    archived = EvidenceReference(**cases["archived-source"]["evidence"])
    assert archived.archived_url.startswith("https://web.archive.org/")
    assert archived.source_type == cases["archived-source"]["expect"]["source_type"]
