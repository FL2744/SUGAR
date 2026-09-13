from __future__ import annotations

import pytest

from sugar_core.llm import LLMConfig
from sugar_core.models import PostRecord
from sugar_core.triage import TriageResult, observation_from_triage, parse_triage_result, triage_posts
from sugar_core.triage_io import post_record_from_mapping


def _post(text: str = "The Confucius Institute will host a student technology workshop in Bishkek.") -> PostRecord:
    return PostRecord(
        platform="bluesky",
        native_id="p1",
        canonical_url="https://example.test/p1",
        query="confucius institute",
        original_text=text,
        translated_text=text,
        published_at="2026-09-10T12:00:00Z",
        author_name="Example Center",
    )


def test_grounded_sensitive_label_is_kept_and_fake_span_is_dropped():
    record = _post("The program criticized U.S. policy and announced a student workshop in Bishkek.")
    raw = {
        "relevance": "relevant",
        "relevance_confidence": 0.92,
        "labels": ["event_activity", "anti_us_explicit", "china_russia_joint_activity"],
        "summary": "A public student workshop was announced and U.S. policy was criticized.",
        "institution_name": "Example Center",
        "program_name": "Student Workshop",
        "actors": ["Example Center"],
        "audiences": ["students"],
        "themes": ["technology"],
        "us_overlap": [],
        "location_label": "Bishkek",
        "reason": "The source explicitly describes the event.",
        "evidence": [
            {"label": "relevance", "span": "announced a student workshop in Bishkek"},
            {"label": "anti_us_explicit", "span": "criticized U.S. policy"},
            {"label": "china_russia_joint_activity", "span": "joint China-Russia program"},
            {"label": "location", "span": "in Bishkek"},
        ],
    }

    result = parse_triage_result(raw, record)

    assert result.relevance == "relevant"
    assert "anti_us_explicit" in result.labels
    assert "china_russia_joint_activity" not in result.labels
    assert result.location_label == "Bishkek"
    assert any(item.label == "anti_us_explicit" for item in result.evidence)
    assert not any(item.label == "china_russia_joint_activity" for item in result.evidence)


def test_ungrounded_relevant_result_is_downgraded_to_uncertain():
    record = _post("General discussion about education.")
    result = parse_triage_result(
        {
            "relevance": "relevant",
            "relevance_confidence": 0.95,
            "labels": ["program_activity"],
            "summary": "Relevant program activity.",
            "evidence": [{"label": "relevance", "span": "text that does not exist"}],
        },
        record,
    )

    assert result.relevance == "uncertain"
    assert result.relevance_confidence == pytest.approx(0.49)
    assert "needs_context" in result.labels
    assert result.evidence == []


def test_us_overlap_requires_matching_grounded_evidence():
    record = _post("The event will be held near an EducationUSA advising center.")
    result = parse_triage_result(
        {
            "relevance": "relevant",
            "relevance_confidence": 0.8,
            "labels": ["us_overlap_explicit"],
            "us_overlap": ["EducationUSA"],
            "evidence": [
                {"label": "relevance", "span": "event will be held"},
                {"label": "us_overlap_explicit", "span": "EducationUSA advising center"},
            ],
        },
        record,
    )
    assert result.us_overlap == ["EducationUSA"]
    assert "us_overlap_explicit" in result.labels


def test_observation_from_triage_populates_review_queue_fields():
    record = _post()
    result = TriageResult(
        relevance="relevant",
        relevance_confidence=0.84,
        labels=["event_activity", "education", "strategic_audience_students"],
        summary="A student technology workshop was announced.",
        institution_name="Confucius Institute",
        program_name="Technology Workshop",
        audiences=["students"],
        themes=["technology", "education"],
        reason="Explicit event announcement.",
    )

    observation = observation_from_triage(record, result, model="test-model")

    assert observation.relevance == "relevant"
    assert observation.relevance_confidence == pytest.approx(0.84)
    assert observation.verification_state == "ai_triaged"
    assert observation.institution_name == "Confucius Institute"
    assert observation.program_name == "Technology Workshop"
    assert observation.audiences == ["students"]
    assert observation.ai_model == "test-model"


def test_legacy_post_row_can_be_rehydrated_for_triage():
    record = post_record_from_mapping(
        {
            "platform": "x",
            "tweet_id": "123",
            "x_url": "https://x.com/example/status/123",
            "date_iso": "2026-09-01T10:00:00Z",
            "username": "example",
            "display_name": "Example",
            "original_text": "Public program announcement",
            "translated_en": "Public program announcement",
            "raw_stats": '{"like_count": 4}',
            "is_retweet": "false",
        }
    )
    assert record.native_id == "123"
    assert record.canonical_url == "https://x.com/example/status/123"
    assert record.author_handle == "example"
    assert record.translated_text == "Public program announcement"
    assert record.raw_stats["like_count"] == 4
    assert record.is_repost is False


def test_batch_triage_failure_becomes_followup_instead_of_aborting(monkeypatch, tmp_path):
    record = _post()
    monkeypatch.setattr("sugar_core.triage.create_client", lambda llm: object())

    def fail(*args, **kwargs):
        raise ValueError("bad model output")

    monkeypatch.setattr("sugar_core.triage.triage_post", fail)
    observations = triage_posts(
        [record],
        llm=LLMConfig(provider="openai", model="test-model", api_key="test-key"),
        cache_dir=tmp_path,
    )

    assert len(observations) == 1
    observation = observations[0]
    assert observation.verification_state == "needs_followup"
    assert observation.relevance == "unknown"
    assert "triage_error" in observation.triage_labels
    assert "needs_context" in observation.triage_labels
    assert "ValueError" in observation.ai_reason
