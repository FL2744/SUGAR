from sugar_core.state_agentic import _evidence_neighborhood


def test_evidence_neighborhood_retrieves_cited_case_and_comparable_neighbors():
    packet = {
        "scope": {"mode": "global"},
        "guardrails": [],
        "corpus": {},
        "macro_structure": {},
        "comparative_diagnostics": {},
        "network_patterns": {},
        "collection_questions": [],
        "representative_cases": [
            {
                "observation_id": "obs_a",
                "assessment_id": "state_a",
                "source_refs": ["https://example.org/a"],
                "high_consequence_claims": [],
                "comparables": [{"observation_id": "obs_b", "similarity": 0.7}],
            },
            {
                "observation_id": "obs_b",
                "assessment_id": "state_b",
                "source_refs": ["https://example.org/b"],
                "high_consequence_claims": [],
                "comparables": [],
            },
        ],
    }
    output = {
        "judgments": [{"supporting_refs": ["obs_a"], "contrary_refs": []}],
        "findings": [],
        "alternatives": [],
    }
    neighborhood = _evidence_neighborhood(packet, output)
    ids = {row["observation_id"] for row in neighborhood["representative_cases"]}
    assert ids == {"obs_a", "obs_b"}
    assert "cited them" in neighborhood["retrieval_note"]
