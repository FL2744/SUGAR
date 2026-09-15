from dataclasses import asdict

import pytest

from sugar_core.state_schema import (
    AnalyticClaim,
    QualifiedReachValue,
    ReachMetrics,
    StateAssessment,
    SupportAssessment,
)


def test_confirmed_prc_support_requires_evidence_and_human_review():
    with pytest.raises(ValueError, match="explicit evidence"):
        SupportAssessment(level="confirmed", review_state="human_verified", reviewer="analyst")

    with pytest.raises(ValueError, match="human verification"):
        SupportAssessment(
            level="confirmed",
            bases=["official_prc_source"],
            evidence_refs=["https://example.org/source"],
            review_state="ai_triaged",
        )

    support = SupportAssessment(
        level="confirmed",
        bases=["official_prc_source"],
        evidence_refs=["https://example.org/source"],
        review_state="human_verified",
        reviewer="analyst",
    )
    assert support.level == "confirmed"


def test_influence_cannot_be_encoded_as_simple_observed_fact():
    with pytest.raises(ValueError, match="simple observed fact"):
        AnalyticClaim(
            statement="The program influenced participants.",
            claim_type="influence",
            epistemic_status="observed_fact",
            evidence_refs=["https://example.org/source"],
        )


def test_high_consequence_claims_require_evidence_references():
    for claim_type in ("support_relationship", "coordination", "influence"):
        with pytest.raises(ValueError, match="explicit evidence"):
            AnalyticClaim(
                statement=f"Test {claim_type}",
                claim_type=claim_type,
                epistemic_status="analytic_assessment",
            )


def test_state_assessment_is_not_brief_eligible_until_human_verified():
    assessment = StateAssessment(observation_id="obs_123", review_state="ai_triaged")
    assert not assessment.brief_eligible

    verified = StateAssessment(
        observation_id="obs_456",
        review_state="human_verified",
        reviewer="analyst",
    )
    assert verified.brief_eligible


def test_approximate_reach_is_structured_without_becoming_exact():
    reach = ReachMetrics(
        qualified={
            "attendance": {
                "value": 300,
                "qualifier": "approximate",
                "source_note": "Source reports roughly 300 participants.",
                "source_ref": "https://example.org/event",
            }
        }
    )

    assert reach.attendance is None
    assert reach.metric("attendance").value == 300
    assert reach.metric("attendance").qualifier == "approximate"
    assert reach.has_nonexact_values
    assert reach.observed_total == 0


def test_minimum_reach_preserves_lower_bound_and_source():
    metric = QualifiedReachValue(
        value=1000,
        qualifier="minimum",
        source_note="Source reports more than 1,000 attendees.",
        source_ref="https://example.org/event",
    )
    assert metric.lower_bound == 1000
    assert metric.upper_bound is None

    reach = ReachMetrics(qualified={"attendance": metric})
    assert reach.attendance is None
    assert reach.metric("attendance").lower_bound == 1000
    assert reach.observed_total == 0


def test_exact_qualified_reach_mirrors_legacy_field_and_round_trips():
    assessment = StateAssessment(
        observation_id="obs_reach",
        reach=ReachMetrics(
            qualified={
                "attendance": QualifiedReachValue(
                    value=13,
                    qualifier="exact",
                    source_ref="https://example.org/competition",
                )
            }
        ),
    )
    assert assessment.reach.attendance == 13
    assert assessment.reach.observed_total == 13

    exported = asdict(assessment)
    restored = StateAssessment.from_dict(exported)
    assert restored.reach.attendance == 13
    assert restored.reach.metric("attendance").qualifier == "exact"
    assert restored.reach.metric("attendance").source_ref == "https://example.org/competition"


def test_nonexact_reach_cannot_also_be_stored_as_bare_exact_integer():
    with pytest.raises(ValueError, match="cannot also be stored as a bare exact integer"):
        ReachMetrics(
            attendance=300,
            qualified={
                "attendance": {
                    "value": 300,
                    "qualifier": "approximate",
                    "source_note": "Source reports roughly 300 participants.",
                }
            },
        )


def test_range_reach_requires_valid_bounds():
    metric = QualifiedReachValue(
        qualifier="range",
        minimum=200,
        maximum=250,
        source_note="Source reports 200–250 participants.",
    )
    assert metric.lower_bound == 200
    assert metric.upper_bound == 250

    with pytest.raises(ValueError, match="minimum cannot exceed maximum"):
        QualifiedReachValue(
            qualifier="range",
            minimum=300,
            maximum=200,
            source_note="Invalid range.",
        )


def test_minimum_and_maximum_qualifiers_reject_contradictory_explicit_bounds():
    with pytest.raises(ValueError, match="Minimum reach bound must equal the reported value"):
        QualifiedReachValue(
            value=1000,
            qualifier="minimum",
            minimum=900,
            source_note="Source reports more than 1,000 attendees.",
        )

    with pytest.raises(ValueError, match="Maximum reach bound must equal the reported value"):
        QualifiedReachValue(
            value=500,
            qualifier="maximum",
            maximum=600,
            source_note="Source reports fewer than 500 attendees.",
        )


def test_qualified_reach_rejects_empty_or_unknown_metric_names():
    for metric_name in ("", "impressions"):
        with pytest.raises(ValueError, match="Unsupported reach metric name"):
            ReachMetrics(
                qualified={
                    metric_name: {
                        "value": 100,
                        "qualifier": "approximate",
                        "source_note": "Approximate source count.",
                    }
                }
            )
