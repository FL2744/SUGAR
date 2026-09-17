from pathlib import Path

import pytest

from sugar_core.state_entities import EntityRegistry, MonitoredEntity, load_entity_registry, save_entity_registry, save_query_plan


def test_registry_resolves_aliases_without_implying_support():
    entity = MonitoredEntity(
        canonical_name="Example Institute",
        entity_type="institution",
        aliases=["EI"],
        native_names=["示例学院"],
        country="Kenya",
        query_terms=["Example Institute robotics"],
        priority="high",
    )
    registry = EntityRegistry([entity])
    assert registry.resolve("EI").entity_id == entity.entity_id
    assert registry.resolve("示例学院").canonical_name == "Example Institute"
    assert not hasattr(entity, "sponsor_support")
    assert [row["query"] for row in registry.query_plan()] == ["Example Institute", "EI", "示例学院", "Example Institute robotics"]


def test_registry_rejects_ambiguous_aliases():
    first = MonitoredEntity(canonical_name="First", aliases=["Shared"], country="A")
    second = MonitoredEntity(canonical_name="Second", aliases=["Shared"], country="B")
    with pytest.raises(ValueError, match="Ambiguous entity alias"):
        EntityRegistry([first, second])


def test_registry_roundtrip_and_query_plan(tmp_path: Path):
    registry = EntityRegistry(
        [
            MonitoredEntity(
                canonical_name="Monitored Program",
                entity_type="program",
                aliases=["MP"],
                country="example_host_country",
                city="Bishkek",
                official_urls=["https://example.org/official"],
                priority="urgent",
            )
        ]
    )
    registry_path = Path(save_entity_registry(registry, tmp_path / "entities.csv"))
    loaded = load_entity_registry(registry_path)
    assert loaded.resolve("MP").canonical_name == "Monitored Program"
    query_path = Path(save_query_plan(loaded, tmp_path / "queries.csv"))
    assert query_path.is_file()
    text = query_path.read_text(encoding="utf-8-sig")
    assert "Monitored Program" in text
    assert "MP" in text
