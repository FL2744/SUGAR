from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ENTITY_TYPES = {
    "prc_government",
    "prc_diplomatic_mission",
    "institution",
    "program",
    "host_institution",
    "partner",
    "media_account",
    "commercial_actor",
    "us_public_diplomacy",
    "other",
}

WATCH_PRIORITIES = {"low", "normal", "high", "urgent"}


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean_list(values: Iterable[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _clean(value)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _entity_id(entity_type: str, canonical_name: str, country: str) -> str:
    identity = f"{entity_type}|{canonical_name}|{country}".casefold().encode("utf-8")
    return "entity_" + hashlib.sha256(identity).hexdigest()[:20]


@dataclass
class MonitoredEntity:
    canonical_name: str
    entity_type: str = "institution"
    entity_id: str = ""
    aliases: list[str] = field(default_factory=list)
    native_names: list[str] = field(default_factory=list)
    country: str = ""
    city: str = ""
    parent_entity_id: str = ""
    official_urls: list[str] = field(default_factory=list)
    social_urls: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    query_terms: list[str] = field(default_factory=list)
    priority: str = "normal"
    active: bool = True
    notes: str = ""

    def __post_init__(self) -> None:
        self.canonical_name = _clean(self.canonical_name)
        if not self.canonical_name:
            raise ValueError("Monitored entities require a canonical_name.")
        self.entity_type = _clean(self.entity_type).casefold() or "institution"
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"Unsupported entity_type: {self.entity_type}")
        self.aliases = _clean_list(self.aliases)
        self.native_names = _clean_list(self.native_names)
        self.country = _clean(self.country)
        self.city = _clean(self.city)
        self.parent_entity_id = _clean(self.parent_entity_id)
        self.official_urls = _clean_list(self.official_urls)
        self.social_urls = _clean_list(self.social_urls)
        self.languages = _clean_list(self.languages)
        self.query_terms = _clean_list(self.query_terms)
        self.priority = _clean(self.priority).casefold() or "normal"
        if self.priority not in WATCH_PRIORITIES:
            raise ValueError(f"Unsupported entity priority: {self.priority}")
        self.notes = _clean(self.notes)
        self.entity_id = _clean(self.entity_id) or _entity_id(self.entity_type, self.canonical_name, self.country)

    @property
    def names(self) -> list[str]:
        return _clean_list([self.canonical_name, *self.aliases, *self.native_names])

    @property
    def watch_terms(self) -> list[str]:
        return _clean_list([*self.names, *self.query_terms])


class EntityRegistry:
    def __init__(self, entities: Iterable[MonitoredEntity] = ()):
        self.entities: dict[str, MonitoredEntity] = {}
        self._alias: dict[str, str] = {}
        for entity in entities:
            self.add(entity)

    def add(self, entity: MonitoredEntity) -> None:
        if entity.entity_id in self.entities:
            raise ValueError(f"Duplicate entity_id: {entity.entity_id}")
        for name in entity.names:
            key = name.casefold()
            existing = self._alias.get(key)
            if existing and existing != entity.entity_id:
                raise ValueError(f"Ambiguous entity alias '{name}' maps to both {existing} and {entity.entity_id}.")
        self.entities[entity.entity_id] = entity
        for name in entity.names:
            self._alias[name.casefold()] = entity.entity_id

    def resolve(self, name: str) -> MonitoredEntity | None:
        entity_id = self._alias.get(_clean(name).casefold())
        return self.entities.get(entity_id) if entity_id else None

    def canonicalize(self, name: str) -> str:
        entity = self.resolve(name)
        return entity.canonical_name if entity else _clean(name)

    def query_plan(self, *, priorities: Iterable[str] = ("normal", "high", "urgent")) -> list[dict[str, Any]]:
        allowed = {str(value).casefold() for value in priorities}
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for entity in sorted(self.entities.values(), key=lambda item: (item.country, item.canonical_name)):
            if not entity.active or entity.priority not in allowed:
                continue
            for term in entity.watch_terms:
                key = (entity.entity_id, term.casefold())
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "entity_id": entity.entity_id,
                        "entity_type": entity.entity_type,
                        "canonical_name": entity.canonical_name,
                        "country": entity.country,
                        "city": entity.city,
                        "priority": entity.priority,
                        "query": term,
                    }
                )
        return rows


def _list_cell(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return _clean_list(data)
        except json.JSONDecodeError:
            pass
    return _clean_list(text.replace("|", ";").split(";"))


def load_entity_registry(path: str | Path) -> EntityRegistry:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.suffix.lower() == ".jsonl":
        entities = []
        for line_number, line in enumerate(source.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entities.append(MonitoredEntity(**json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid entity JSON on line {line_number}") from exc
        return EntityRegistry(entities)
    if source.suffix.lower() != ".csv":
        raise ValueError("Entity registry must be CSV or JSONL.")
    with source.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    entities = []
    for row in rows:
        entities.append(
            MonitoredEntity(
                entity_id=_clean(row.get("entity_id")),
                canonical_name=_clean(row.get("canonical_name")),
                entity_type=_clean(row.get("entity_type")) or "institution",
                aliases=_list_cell(row.get("aliases")),
                native_names=_list_cell(row.get("native_names")),
                country=_clean(row.get("country")),
                city=_clean(row.get("city")),
                parent_entity_id=_clean(row.get("parent_entity_id")),
                official_urls=_list_cell(row.get("official_urls")),
                social_urls=_list_cell(row.get("social_urls")),
                languages=_list_cell(row.get("languages")),
                query_terms=_list_cell(row.get("query_terms")),
                priority=_clean(row.get("priority")) or "normal",
                active=_clean(row.get("active")).casefold() not in {"false", "0", "no", "inactive"},
                notes=_clean(row.get("notes")),
            )
        )
    return EntityRegistry(entities)


def save_entity_registry(registry: EntityRegistry, path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() == ".jsonl":
        with target.open("w", encoding="utf-8") as stream:
            for entity in registry.entities.values():
                stream.write(json.dumps(asdict(entity), ensure_ascii=False, sort_keys=True) + "\n")
        return str(target.resolve())
    if target.suffix.lower() != ".csv":
        target = target.with_suffix(".csv")
    fields = [
        "entity_id",
        "canonical_name",
        "entity_type",
        "aliases",
        "native_names",
        "country",
        "city",
        "parent_entity_id",
        "official_urls",
        "social_urls",
        "languages",
        "query_terms",
        "priority",
        "active",
        "notes",
    ]
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for entity in registry.entities.values():
            raw = asdict(entity)
            for key in ("aliases", "native_names", "official_urls", "social_urls", "languages", "query_terms"):
                raw[key] = "; ".join(raw[key])
            writer.writerow(raw)
    return str(target.resolve())


def write_entity_template(path: str | Path) -> str:
    registry = EntityRegistry(
        [
            MonitoredEntity(
                canonical_name="Example monitored institution",
                entity_type="institution",
                aliases=["Example alias"],
                native_names=["本地名称示例"],
                country="Example Country",
                city="Example City",
                official_urls=["https://example.org/official"],
                languages=["English", "Chinese", "Local language"],
                query_terms=["Example program name"],
                priority="high",
                notes="Replace this row with verified entities and aliases; aliases are discovery aids, not proof of PRC support.",
            )
        ]
    )
    return save_entity_registry(registry, path)


def save_query_plan(registry: EntityRegistry, path: str | Path) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fields = ["entity_id", "entity_type", "canonical_name", "country", "city", "priority", "query"]
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(registry.query_plan())
    return str(target.resolve())
