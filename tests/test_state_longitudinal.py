from sugar_core.state_longitudinal import compare_intelligence_packets, compare_syntheses


def test_synthesis_comparison_tracks_likelihood_confidence_and_evidence_changes():
    previous = {
        "generated_at": "2026-08-01T00:00:00Z",
        "final": {
            "key_judgments": [
                {
                    "judgment_id": "j_same",
                    "statement": "Observed programming is recurring.",
                    "likelihood": "likely",
                    "confidence": "low",
                    "supporting_refs": ["obs_a"],
                    "contrary_refs": [],
                }
            ]
        },
    }
    current = {
        "generated_at": "2026-09-01T00:00:00Z",
        "final": {
            "key_judgments": [
                {
                    "judgment_id": "j_same",
                    "statement": "Observed programming is recurring.",
                    "likelihood": "very_likely",
                    "confidence": "moderate",
                    "supporting_refs": ["obs_a", "obs_b"],
                    "contrary_refs": [],
                },
                {
                    "judgment_id": "j_new",
                    "statement": "A new pattern emerged.",
                    "likelihood": "roughly_even_chance",
                    "confidence": "low",
                    "supporting_refs": ["obs_c"],
                    "contrary_refs": [],
                },
            ]
        },
    }
    result = compare_syntheses(previous, current)
    assert result["summary"]["added"] == 1
    assert result["summary"]["changed"] == 1
    changed = result["changed_judgments"][0]
    assert changed["likelihood_change"] == "strengthened"
    assert changed["confidence_change"] == "strengthened"
    assert changed["changed_fields"]["supporting_refs"]["added"] == ["obs_b"]


def test_packet_comparison_marks_corpus_distribution_change_as_descriptive():
    previous = {
        "corpus": {"observations": 10, "assessments": 10, "verified_brief_eligible": 5},
        "macro_structure": {
            "countries": [{"value": "A", "share": 0.8}, {"value": "B", "share": 0.2}],
            "program_domains": [{"value": "higher_education", "share": 1.0}],
        },
        "temporal": {"signals": []},
    }
    current = {
        "corpus": {"observations": 20, "assessments": 20, "verified_brief_eligible": 12},
        "macro_structure": {
            "countries": [{"value": "A", "share": 0.5}, {"value": "B", "share": 0.5}],
            "program_domains": [
                {"value": "higher_education", "share": 0.6},
                {"value": "stem_technology", "share": 0.4},
            ],
        },
        "temporal": {"signals": [{"signal": "observed_geographic_broadening_candidate"}]},
    }
    result = compare_intelligence_packets(previous, current)
    assert result["corpus_delta"]["observations"]["delta"] == 10
    assert result["distribution_deltas"]["countries"]
    assert "not coverage-adjusted" in result["guardrails"][0]
    assert result["new_temporal_signals"] == ["observed_geographic_broadening_candidate"]
