from sugar_core.state_hypotheses import build_hypothesis_matrix


def test_hypothesis_matrix_surfaces_discriminating_evidence_without_probability_claims():
    synthesis = {
        "scope": {"mode": "global"},
        "final": {
            "alternatives": [
                {
                    "hypothesis": "Observed recurrence reflects coordinated program expansion.",
                    "supporting_refs": ["obs_a", "obs_b"],
                    "contradicting_refs": ["obs_c"],
                    "discriminators": ["Find explicit coordination evidence."],
                    "collection_needed": ["Host-side documentation."],
                },
                {
                    "hypothesis": "Observed recurrence reflects independent local partner choices.",
                    "supporting_refs": ["obs_c"],
                    "contradicting_refs": ["obs_a"],
                    "discriminators": ["Compare local planning records."],
                    "collection_needed": ["Local partner interviews or public records."],
                },
            ]
        },
        "agents": [],
    }
    result = build_hypothesis_matrix(synthesis)
    assert len(result["hypotheses"]) == 2
    refs = {row["evidence_ref"] for row in result["discriminating_evidence"]}
    assert "obs_a" in refs
    assert "obs_c" in refs
    assert result["least_inconsistent_ranking"]
    assert "not a probability" in result["least_inconsistent_ranking"][0]["least_inconsistent_rank_basis"]
    assert "not a probability estimate" in result["guardrails"][0]
