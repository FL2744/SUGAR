"""Team review of collected items: a verdict, tags and a comment thread per item.

Review state is an append-only log (``review.jsonl``) in the project, so nothing is overwritten and every
change shows who made it and when. State for an item is derived by replaying its events:

* ``verdict`` - one of ``relevant``, ``not_relevant``, ``follow_up`` (latest wins; absent = unreviewed)
* ``tags``    - added and removed one at a time
* ``comments``- the discussion, oldest first

Items keep their id across runs, so a verdict given in one run is still there after a rerun or refresh.
The author is always supplied by the server from the authenticated member; a client cannot choose it.
"""
from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .research_plan import utc_now

VERDICTS = ("relevant", "not_relevant", "follow_up")
MAX_COMMENT = 4000
MAX_TAGS_PER_ITEM = 20


def _clean_tag(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lstrip("#")).casefold()[:40]


def _empty() -> dict[str, Any]:
    return {"verdict": "", "verdict_by": "", "verdict_at": "", "tags": [], "comments": []}


def replay(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for event in events:
        item_id = str(event.get("item_id") or "")
        if not item_id:
            continue
        row = state.setdefault(item_id, _empty())
        kind = event.get("kind")
        if kind == "verdict":
            row["verdict"], row["verdict_by"], row["verdict_at"] = str(event.get("verdict") or ""), str(event.get("author") or ""), str(event.get("at") or "")
        elif kind == "tag_add" and event.get("tag") and event["tag"] not in row["tags"]:
            row["tags"].append(event["tag"])
        elif kind == "tag_remove" and event.get("tag") in row["tags"]:
            row["tags"].remove(event["tag"])
        elif kind == "comment":
            row["comments"].append({"id": event.get("id", ""), "author": event.get("author", ""), "text": event.get("text", ""), "at": event.get("at", "")})
    return state


class ReviewStore:
    def __init__(self, project: Any) -> None:
        self.project = project

    @property
    def _path(self):
        return self.project.root / "review.jsonl"

    def events(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        try:
            lines = self._path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return out
        for line in lines:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
        return out

    def _append(self, event: dict[str, Any]) -> None:
        with self.project._lock:
            self.project.root.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")

    def state(self, item_id: str = "") -> dict[str, Any]:
        replayed = replay(self.events())
        return replayed.get(item_id, _empty()) if item_id else replayed

    def summary(self, item_ids: set[str] | None = None) -> dict[str, Any]:
        """Counts for the Results filters: items per verdict, per tag, and with discussion (optionally only these items)."""
        replayed = replay(self.events())
        if item_ids is not None:
            replayed = {k: v for k, v in replayed.items() if k in item_ids}
        verdicts = {v: 0 for v in VERDICTS}
        tags: dict[str, int] = {}
        for row in replayed.values():
            if row["verdict"] in verdicts:
                verdicts[row["verdict"]] += 1
            for tag in row["tags"]:
                tags[tag] = tags.get(tag, 0) + 1
        return {"verdicts": verdicts, "tags": dict(sorted(tags.items(), key=lambda kv: (-kv[1], kv[0]))),
                "commented": sum(1 for r in replayed.values() if r["comments"]), "reviewed": sum(1 for r in replayed.values() if r["verdict"])}

    def apply(self, item_id: str, action: dict[str, Any], *, author: str) -> dict[str, Any]:
        item_id = str(item_id or "").strip()
        if not item_id:
            raise ValueError("An item id is required.")
        kind = str(action.get("kind") or "")
        event: dict[str, Any] = {"id": f"rv_{uuid.uuid4().hex[:10]}", "item_id": item_id, "author": author or "member", "at": utc_now(), "kind": kind}
        if kind == "verdict":
            verdict = str(action.get("verdict") or "")
            if verdict and verdict not in VERDICTS:
                raise ValueError(f"A verdict must be one of: {', '.join(VERDICTS)} (or empty to clear).")
            event["verdict"] = verdict
        elif kind in {"tag_add", "tag_remove"}:
            tag = _clean_tag(action.get("tag"))
            if not tag:
                raise ValueError("A tag cannot be empty.")
            if kind == "tag_add" and len(self.state(item_id)["tags"]) >= MAX_TAGS_PER_ITEM:
                raise ValueError(f"An item can have at most {MAX_TAGS_PER_ITEM} tags.")
            event["tag"] = tag
        elif kind == "comment":
            text = str(action.get("text") or "").strip()
            if not text:
                raise ValueError("A comment cannot be empty.")
            event["text"] = text[:MAX_COMMENT]
        else:
            raise ValueError("Unknown review action.")
        self._append(event)
        self.project.log("item_reviewed", {"item_id": item_id, "action": kind, **({"verdict": event["verdict"]} if kind == "verdict" else {})}, actor=event["author"])
        return self.state(item_id)
