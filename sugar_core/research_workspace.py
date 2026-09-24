from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

RESEARCH_STATE_FILENAME = "sugar-research.json"
RESEARCH_STATE_SCHEMA_VERSION = "1.0"

SUBPROJECT_STATUSES = {"active", "paused", "complete", "archived"}
LISTENING_POST_STATUSES = {"active", "paused", "archived"}
REFERENCE_LAYER_TYPES = {"institution", "site", "event", "boundary", "custom"}
ENTITY_LIFECYCLE_STATUSES = {"active", "closed", "renamed", "relocated", "planned", "unknown"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clean_list(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = _clean(value)
        key = text.casefold()
        if text and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


@dataclass
class Subproject:
    name: str
    subproject_id: str = ""
    description: str = ""
    parent_subproject_id: str = ""
    status: str = "active"
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = _clean(self.name)
        if not self.name:
            raise ValueError("Subprojects require a name.")
        self.subproject_id = _clean(self.subproject_id) or _id("subproject")
        self.description = _clean(self.description)
        self.parent_subproject_id = _clean(self.parent_subproject_id)
        self.status = _clean(self.status).casefold() or "active"
        if self.status not in SUBPROJECT_STATUSES:
            raise ValueError(f"Unsupported subproject status: {self.status}")
        self.tags = _clean_list(self.tags)
        now = _utc_now()
        self.created_at = _clean(self.created_at) or now
        self.updated_at = _clean(self.updated_at) or self.created_at


@dataclass
class SearchHistoryEntry:
    query_terms: list[str]
    sources: list[str]
    history_id: str = ""
    subproject_id: str = ""
    research_question: str = ""
    started_at: str = ""
    completed_at: str = ""
    result_count: int | None = None
    status: str = "complete"
    collection_id: str = ""
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.history_id = _clean(self.history_id) or _id("search")
        self.query_terms = _clean_list(self.query_terms)
        self.sources = _clean_list(self.sources)
        if not self.query_terms:
            raise ValueError("Search history requires at least one query term.")
        self.subproject_id = _clean(self.subproject_id)
        self.research_question = _clean(self.research_question)
        self.started_at = _clean(self.started_at) or _utc_now()
        self.completed_at = _clean(self.completed_at)
        self.status = _clean(self.status).casefold() or "complete"
        self.collection_id = _clean(self.collection_id)
        self.notes = _clean(self.notes)
        if self.result_count is not None:
            self.result_count = int(self.result_count)
            if self.result_count < 0:
                raise ValueError("result_count cannot be negative.")
        if not isinstance(self.metadata, dict):
            raise ValueError("Search history metadata must be an object.")


@dataclass
class ListeningPost:
    name: str
    query_terms: list[str]
    sources: list[str]
    listening_post_id: str = ""
    subproject_id: str = ""
    entity_ids: list[str] = field(default_factory=list)
    status: str = "active"
    cadence: str = "manual"
    created_at: str = ""
    updated_at: str = ""
    last_run_at: str = ""
    last_success_at: str = ""
    baseline_start: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = _clean(self.name)
        if not self.name:
            raise ValueError("Listening posts require a name.")
        self.listening_post_id = _clean(self.listening_post_id) or _id("listen")
        self.query_terms = _clean_list(self.query_terms)
        self.sources = _clean_list(self.sources)
        self.entity_ids = _clean_list(self.entity_ids)
        if not self.query_terms and not self.entity_ids:
            raise ValueError("Listening posts require query terms or watched entities.")
        self.subproject_id = _clean(self.subproject_id)
        self.status = _clean(self.status).casefold() or "active"
        if self.status not in LISTENING_POST_STATUSES:
            raise ValueError(f"Unsupported listening-post status: {self.status}")
        self.cadence = _clean(self.cadence) or "manual"
        now = _utc_now()
        self.created_at = _clean(self.created_at) or now
        self.updated_at = _clean(self.updated_at) or self.created_at
        self.last_run_at = _clean(self.last_run_at)
        self.last_success_at = _clean(self.last_success_at)
        self.baseline_start = _clean(self.baseline_start)
        if not isinstance(self.metadata, dict):
            raise ValueError("Listening-post metadata must be an object.")


@dataclass
class ReferenceLayer:
    name: str
    source: str
    layer_id: str = ""
    layer_type: str = "custom"
    subproject_id: str = ""
    visible_by_default: bool = True
    style: dict[str, Any] = field(default_factory=dict)
    field_mapping: dict[str, str] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.name = _clean(self.name)
        self.source = _clean(self.source)
        if not self.name or not self.source:
            raise ValueError("Reference layers require name and source.")
        self.layer_id = _clean(self.layer_id) or _id("layer")
        self.layer_type = _clean(self.layer_type).casefold() or "custom"
        if self.layer_type not in REFERENCE_LAYER_TYPES:
            raise ValueError(f"Unsupported reference layer type: {self.layer_type}")
        self.subproject_id = _clean(self.subproject_id)
        now = _utc_now()
        self.created_at = _clean(self.created_at) or now
        self.updated_at = _clean(self.updated_at) or self.created_at
        if not isinstance(self.style, dict) or not isinstance(self.field_mapping, dict) or not isinstance(self.metadata, dict):
            raise ValueError("Reference-layer style, field_mapping, and metadata must be objects.")


@dataclass
class CollaborationMember:
    display_name: str
    member_id: str = ""
    role: str = "analyst"
    contact: str = ""
    added_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.display_name = _clean(self.display_name)
        if not self.display_name:
            raise ValueError("Collaboration members require a display name.")
        self.member_id = _clean(self.member_id) or _id("member")
        self.role = _clean(self.role).casefold() or "analyst"
        self.contact = _clean(self.contact)
        self.added_at = _clean(self.added_at) or _utc_now()
        if not isinstance(self.metadata, dict):
            raise ValueError("Collaboration member metadata must be an object.")


@dataclass
class ConversationMessage:
    record_key: str
    author: str
    text: str
    platform: str = ""
    conversation_id: str = ""
    parent_record_key: str = ""
    published_at: str = ""
    url: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ResearchWorkspaceState:
    """Portable analyst-facing project state stored beside the workspace manifest."""

    def __init__(
        self,
        root: str | Path,
        *,
        project_id: str,
        subprojects: Iterable[Subproject] = (),
        search_history: Iterable[SearchHistoryEntry] = (),
        listening_posts: Iterable[ListeningPost] = (),
        reference_layers: Iterable[ReferenceLayer] = (),
        collaborators: Iterable[CollaborationMember] = (),
        created_at: str = "",
        updated_at: str = "",
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.project_id = _clean(project_id)
        if not self.project_id:
            raise ValueError("Research workspace state requires project_id.")
        self.subprojects = {item.subproject_id: item for item in subprojects}
        self.search_history = list(search_history)
        self.listening_posts = {item.listening_post_id: item for item in listening_posts}
        self.reference_layers = {item.layer_id: item for item in reference_layers}
        self.collaborators = {item.member_id: item for item in collaborators}
        now = _utc_now()
        self.created_at = _clean(created_at) or now
        self.updated_at = _clean(updated_at) or self.created_at
        self._validate_links()

    @property
    def path(self) -> Path:
        return self.root / RESEARCH_STATE_FILENAME

    @classmethod
    def create(cls, root: str | Path, *, project_id: str) -> "ResearchWorkspaceState":
        state = cls(root, project_id=project_id)
        state.save()
        return state

    @classmethod
    def open(cls, root: str | Path, *, project_id: str) -> "ResearchWorkspaceState":
        root_path = Path(root).expanduser().resolve()
        path = root_path / RESEARCH_STATE_FILENAME
        if not path.is_file():
            return cls.create(root_path, project_id=project_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Research workspace state must contain a JSON object.")
        if str(payload.get("schema_version") or "") != RESEARCH_STATE_SCHEMA_VERSION:
            raise ValueError("Unsupported research workspace state schema.")
        if str(payload.get("project_id") or "") != str(project_id):
            raise ValueError("Research workspace state project_id does not match the workspace.")
        return cls(
            root_path,
            project_id=project_id,
            subprojects=[Subproject(**item) for item in payload.get("subprojects") or []],
            search_history=[SearchHistoryEntry(**item) for item in payload.get("search_history") or []],
            listening_posts=[ListeningPost(**item) for item in payload.get("listening_posts") or []],
            reference_layers=[ReferenceLayer(**item) for item in payload.get("reference_layers") or []],
            collaborators=[CollaborationMember(**item) for item in payload.get("collaborators") or []],
            created_at=str(payload.get("created_at") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def _validate_links(self) -> None:
        known = set(self.subprojects)
        for subproject in self.subprojects.values():
            if subproject.parent_subproject_id and subproject.parent_subproject_id not in known:
                raise ValueError(f"Unknown parent subproject: {subproject.parent_subproject_id}")
            if subproject.parent_subproject_id == subproject.subproject_id:
                raise ValueError("Subprojects cannot parent themselves.")
        for item in [*self.listening_posts.values(), *self.reference_layers.values()]:
            if item.subproject_id and item.subproject_id not in known:
                raise ValueError(f"Unknown subproject: {item.subproject_id}")
        for item in self.search_history:
            if item.subproject_id and item.subproject_id not in known:
                raise ValueError(f"Unknown subproject: {item.subproject_id}")

    def save(self) -> str:
        self.updated_at = _utc_now()
        payload = {
            "schema_version": RESEARCH_STATE_SCHEMA_VERSION,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "subprojects": [asdict(item) for item in self.subprojects.values()],
            "search_history": [asdict(item) for item in self.search_history],
            "listening_posts": [asdict(item) for item in self.listening_posts.values()],
            "reference_layers": [asdict(item) for item in self.reference_layers.values()],
            "collaborators": [asdict(item) for item in self.collaborators.values()],
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.path)
        return str(self.path)

    def add_subproject(self, subproject: Subproject) -> Subproject:
        if subproject.subproject_id in self.subprojects:
            raise ValueError(f"Duplicate subproject_id: {subproject.subproject_id}")
        if subproject.parent_subproject_id and subproject.parent_subproject_id not in self.subprojects:
            raise ValueError(f"Unknown parent subproject: {subproject.parent_subproject_id}")
        self.subprojects[subproject.subproject_id] = subproject
        self.save()
        return subproject

    def record_search(self, entry: SearchHistoryEntry) -> SearchHistoryEntry:
        if entry.subproject_id and entry.subproject_id not in self.subprojects:
            raise ValueError(f"Unknown subproject: {entry.subproject_id}")
        self.search_history.append(entry)
        self.save()
        return entry

    def upsert_listening_post(self, post: ListeningPost) -> ListeningPost:
        if post.subproject_id and post.subproject_id not in self.subprojects:
            raise ValueError(f"Unknown subproject: {post.subproject_id}")
        existing = self.listening_posts.get(post.listening_post_id)
        if existing:
            post.created_at = existing.created_at
            post.updated_at = _utc_now()
        self.listening_posts[post.listening_post_id] = post
        self.save()
        return post

    def upsert_reference_layer(self, layer: ReferenceLayer) -> ReferenceLayer:
        if layer.subproject_id and layer.subproject_id not in self.subprojects:
            raise ValueError(f"Unknown subproject: {layer.subproject_id}")
        existing = self.reference_layers.get(layer.layer_id)
        if existing:
            layer.created_at = existing.created_at
            layer.updated_at = _utc_now()
        self.reference_layers[layer.layer_id] = layer
        self.save()
        return layer

    def upsert_collaborator(self, member: CollaborationMember) -> CollaborationMember:
        self.collaborators[member.member_id] = member
        self.save()
        return member

    def dashboard(self) -> dict[str, Any]:
        active_posts = [p for p in self.listening_posts.values() if p.status == "active"]
        return {
            "project_id": self.project_id,
            "subproject_count": len(self.subprojects),
            "active_subproject_count": sum(1 for s in self.subprojects.values() if s.status == "active"),
            "search_count": len(self.search_history),
            "listening_post_count": len(self.listening_posts),
            "active_listening_post_count": len(active_posts),
            "reference_layer_count": len(self.reference_layers),
            "collaborator_count": len(self.collaborators),
            "updated_at": self.updated_at,
        }


def build_conversations(records: Iterable[dict[str, Any]]) -> list[list[ConversationMessage]]:
    """Reconstruct readable conversations without flattening speaker identity."""
    messages: list[ConversationMessage] = []
    by_key: dict[str, ConversationMessage] = {}
    children: dict[str, list[ConversationMessage]] = {}

    for raw in records:
        key = _clean(raw.get("record_key") or raw.get("id") or raw.get("native_id"))
        if not key:
            continue
        author = _clean(
            raw.get("author_display_name")
            or raw.get("author_name")
            or raw.get("author_handle")
            or raw.get("handle")
            or raw.get("account")
            or "Unknown"
        )
        handle = _clean(raw.get("author_handle") or raw.get("handle"))
        if handle and handle.casefold() not in author.casefold():
            author = f"{author} ({handle})"
        message = ConversationMessage(
            record_key=key,
            author=author,
            text=str(raw.get("text") or raw.get("content") or ""),
            platform=_clean(raw.get("platform")),
            conversation_id=_clean(raw.get("conversation_id") or raw.get("thread_id")),
            parent_record_key=_clean(raw.get("parent_record_key") or raw.get("in_reply_to_record_key") or raw.get("parent_id")),
            published_at=_clean(raw.get("published_at") or raw.get("created_at")),
            url=_clean(raw.get("url") or raw.get("canonical_url")),
            metadata={k: v for k, v in raw.items() if k not in {
                "record_key", "id", "native_id", "author_display_name", "author_name",
                "author_handle", "handle", "account", "text", "content", "platform",
                "conversation_id", "thread_id", "parent_record_key",
                "in_reply_to_record_key", "parent_id", "published_at", "created_at",
                "url", "canonical_url",
            }},
        )
        messages.append(message)
        by_key[key] = message

    for message in messages:
        if message.parent_record_key and message.parent_record_key in by_key:
            children.setdefault(message.parent_record_key, []).append(message)

    roots = [
        message for message in messages
        if not message.parent_record_key or message.parent_record_key not in by_key
    ]

    grouped: dict[str, list[ConversationMessage]] = {}
    for root in roots:
        group_key = root.conversation_id or root.record_key
        ordered: list[ConversationMessage] = []

        def walk(item: ConversationMessage) -> None:
            ordered.append(item)
            for child in sorted(children.get(item.record_key, []), key=lambda m: (m.published_at, m.record_key)):
                walk(child)

        walk(root)
        grouped.setdefault(group_key, []).extend(ordered)

    ungrouped = {m.record_key for group in grouped.values() for m in group}
    for message in messages:
        if message.record_key not in ungrouped:
            grouped.setdefault(message.conversation_id or message.record_key, []).append(message)

    return [
        sorted(group, key=lambda m: (m.published_at, m.record_key))
        for _, group in sorted(grouped.items(), key=lambda item: item[0])
    ]
