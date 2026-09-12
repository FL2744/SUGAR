from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .bilibili import collect_bilibili_public
from .collectors import (
    collect_bluesky,
    collect_mastodon,
    collect_x,
    create_bluesky_access_token,
    create_session,
)
from .models import PostRecord


@dataclass(frozen=True)
class CollectorCapabilities:
    keyword_search: bool = False
    known_item: bool = False
    comments: bool = False
    profile_timeline: bool = False
    authenticated_search: bool = False
    anonymous_search: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "keyword_search": self.keyword_search,
            "known_item": self.known_item,
            "comments": self.comments,
            "profile_timeline": self.profile_timeline,
            "authenticated_search": self.authenticated_search,
            "anonymous_search": self.anonymous_search,
        }


@dataclass
class CollectorRequest:
    search_terms: list[str]
    since: str | None = None
    until: str | None = None
    max_posts_per_query: int = 10
    max_pages_per_query: int = 1
    config: dict[str, Any] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)


SearchAdapter = Callable[[CollectorRequest], list[PostRecord]]


@dataclass(frozen=True)
class CollectorSpec:
    name: str
    capabilities: CollectorCapabilities
    search: SearchAdapter | None = None
    required_secrets: tuple[str, ...] = ()
    description: str = ""

    def validate_search(self, request: CollectorRequest) -> None:
        if not self.capabilities.keyword_search or self.search is None:
            raise ValueError(f"{self.name} does not currently support keyword search in SUGAR.")
        missing = [key for key in self.required_secrets if not request.secrets.get(key, "").strip()]
        if missing:
            names = ", ".join(missing)
            raise ValueError(f"{self.name} requires credential(s): {names}.")


def _common(request: CollectorRequest) -> dict[str, Any]:
    return {
        "search_terms": request.search_terms,
        "since": request.since,
        "until": request.until,
        "max_posts_per_query": request.max_posts_per_query,
        "max_pages_per_query": request.max_pages_per_query,
    }


def _collect_x(request: CollectorRequest) -> list[PostRecord]:
    return collect_x(
        bearer_token=request.secrets.get("x_bearer_token", ""),
        search_mode=request.config.get("x_search_mode", "recent"),
        post_languages=request.config.get("post_languages") or [],
        include_reposts=bool(request.config.get("include_retweets", False)),
        **_common(request),
    )


def _collect_bluesky(request: CollectorRequest) -> list[PostRecord]:
    jwt = ""
    identifier = request.secrets.get("bluesky_identifier", "")
    password = request.secrets.get("bluesky_app_password", "")
    if identifier and password:
        jwt = create_bluesky_access_token(create_session(), identifier, password)
    return collect_bluesky(access_jwt=jwt, **_common(request))


def _collect_mastodon(request: CollectorRequest) -> list[PostRecord]:
    return collect_mastodon(
        instance_url=request.config.get("mastodon_url", "https://mastodon.social"),
        access_token=request.secrets.get("mastodon_token", ""),
        include_reposts=bool(request.config.get("include_retweets", False)),
        **_common(request),
    )


def _collect_bilibili(request: CollectorRequest) -> list[PostRecord]:
    return collect_bilibili_public(
        order=request.config.get("bilibili_order", "pubdate"),
        hydrate_details=bool(request.config.get("bilibili_hydrate_details", True)),
        initialize_session=bool(request.config.get("bilibili_initialize_session", True)),
        **_common(request),
    )


COLLECTORS: dict[str, CollectorSpec] = {
    "x": CollectorSpec(
        name="x",
        search=_collect_x,
        required_secrets=("x_bearer_token",),
        capabilities=CollectorCapabilities(
            keyword_search=True,
            known_item=False,
            comments=False,
            profile_timeline=False,
            authenticated_search=True,
            anonymous_search=False,
        ),
        description="X API recent/full-archive search.",
    ),
    "bluesky": CollectorSpec(
        name="bluesky",
        search=_collect_bluesky,
        capabilities=CollectorCapabilities(
            keyword_search=True,
            known_item=False,
            comments=False,
            profile_timeline=False,
            authenticated_search=True,
            anonymous_search=True,
        ),
        description="Bluesky AppView search, optionally authenticated through a PDS app password.",
    ),
    "mastodon": CollectorSpec(
        name="mastodon",
        search=_collect_mastodon,
        capabilities=CollectorCapabilities(
            keyword_search=True,
            known_item=False,
            comments=False,
            profile_timeline=False,
            authenticated_search=True,
            anonymous_search=True,
        ),
        description="Instance-scoped Mastodon status search.",
    ),
    "bilibili": CollectorSpec(
        name="bilibili",
        search=_collect_bilibili,
        capabilities=CollectorCapabilities(
            keyword_search=True,
            known_item=True,
            comments=True,
            profile_timeline=False,
            authenticated_search=False,
            anonymous_search=True,
        ),
        description="Fail-closed public Bilibili video search; known-video and comments helpers are also available.",
    ),
}


def get_collector(name: str) -> CollectorSpec:
    key = str(name or "").strip().lower()
    try:
        return COLLECTORS[key]
    except KeyError as exc:
        raise ValueError(f"Unsupported source: {key or name}") from exc


def collector_capabilities() -> dict[str, dict[str, bool]]:
    return {name: spec.capabilities.as_dict() for name, spec in sorted(COLLECTORS.items())}


def collect_registered_source(name: str, request: CollectorRequest) -> list[PostRecord]:
    spec = get_collector(name)
    spec.validate_search(request)
    assert spec.search is not None
    return spec.search(request)
