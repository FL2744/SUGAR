import json
from pathlib import Path

from sugar_core.observations import EvidenceReference, ResearchObservation
from sugar_core.state_map import create_state_map
from sugar_core.state_schema import StateAssessment, USPresenceSite


def test_state_map_labels_density_as_activity_not_influence(tmp_path: Path):
    observation = ResearchObservation(
        observation_type="event",
        title="Verified event",
        summary="Verified evidence",
        country="Kenya",
        city="Nairobi",
        latitude=-1.2864,
        longitude=36.8172,
        evidence=[EvidenceReference(url="https://example.org/event")],
        verification_state="human_verified",
        reviewer="analyst",
    )
    assessment = StateAssessment(
        observation_id=observation.observation_id,
        review_state="human_verified",
        reviewer="analyst",
    )
    site = USPresenceSite(
        name="American Space Nairobi",
        network="american_space",
        country="Kenya",
        city="Nairobi",
        latitude=-1.29,
        longitude=36.82,
    )
    path = Path(create_state_map([observation], [assessment], tmp_path / "map.html", us_sites=[site]))
    assert path.is_file()
    html = path.read_text(encoding="utf-8")
    assert "not an influence heatmap" in html
    assert "Verified PRC-network observations" in html
    metadata = json.loads((tmp_path / "map.html.metadata.json").read_text(encoding="utf-8"))
    assert metadata["mapped_observations"] == 1
    assert metadata["density_semantics"].endswith("not influence")
