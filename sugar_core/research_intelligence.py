from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

from .models import PostRecord
from .observations import ResearchObservation
from .research_requirements import ResearchRequirement, SearchBranch, SearchPlan
from .state_schema import StateAssessment

RESEARCH_INTELLIGENCE_SCHEMA = "1.0"
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _tokens(value: str) -> set[str]:
    return {item.casefold() for item in _WORD.findall(_clean(value)) if len(item) > 1}


def _stable_id(prefix: str, *parts: Any) -> str:
    payload = "|".join(_clean(item).casefold() for item in parts)
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _host(url: str) -> str:
    try:
        value = (urlsplit(_clean(url)).hostname or "").casefold().removeprefix("www.")
        return value
    except ValueError:
        return ""


def _matching_dimensions(query: str, dimensions: dict[str, list[str]]) -> list[dict[str, str]]:
    query_tokens = _tokens(query)
    matched: list[dict[str, str]] = []
    normalized_query = " ".join(query.casefold().split())
    for dimension, values in dimensions.items():
        for value in values:
            normalized_value = " ".join(value.casefold().split())
            value_tokens = _tokens(value)
            query_roots = {token[:-1] if token.endswith("s") and len(token) > 3 else token for token in query_tokens}
            value_roots = {token[:-1] if token.endswith("s") and len(token) > 3 else token for token in value_tokens}
            if normalized_value and (
                normalized_value in normalized_query
                or (value_tokens and value_tokens.issubset(query_tokens))
                or (value_roots and value_roots.issubset(query_roots))
            ):
                matched.append({"dimension": dimension, "value": value})
    return matched


def _hypotheses(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get("hypotheses") or (payload.get("final") or {}).get("alternatives") or []
    result: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        statement = _clean(item.get("hypothesis"))
        collection = item.get("collection_needed") or []
        if not statement:
            continue
        result.append({
            "hypothesis_id": _clean(item.get("hypothesis_id")) or _stable_id("h", statement),
            "hypothesis": statement,
            "collection_needed": [_clean(value) for value in collection if _clean(value)],
            "discriminators": [_clean(value) for value in item.get("discriminators") or [] if _clean(value)],
        })
    return result


def build_next_evidence_recommendation(
    requirement: ResearchRequirement,
    plan: SearchPlan,
    *,
    hypotheses: dict[str, Any] | None = None,
    max_queries: int = 10,
    max_records_per_query: int = 300,
) -> dict[str, Any]:
    """Rank inspectable collection actions using measured plan metrics and explicit proxies."""
    if requirement.requirement_id != plan.requirement_id:
        raise ValueError("Search plan and research requirement IDs do not match.")
    if not 1 <= int(max_queries) <= 100:
        raise ValueError("max_queries must be between 1 and 100.")
    if not 1 <= int(max_records_per_query) <= 10000:
        raise ValueError("max_records_per_query must be between 1 and 10000.")

    hypothesis_rows = _hypotheses(hypotheses)
    dimensions = {
        "geography": requirement.geographies,
        "audience": requirement.target_audiences,
        "language": [value for value in requirement.languages if value.casefold() != "auto"],
        "known_entity": requirement.known_entities,
    }
    completed_queries = [
        branch.query for branch in plan.branches
        if branch.status == "completed" and branch.metrics.retrieved > 0
    ]
    open_dimensions = [
        {"dimension": kind, "value": value}
        for kind, values in dimensions.items()
        for value in values
        if not any(_matching_dimensions(query, {kind: [value]}) for query in completed_queries)
    ]

    candidates: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    for branch in plan.branches:
        if branch.status not in {"planned", "approved", "paused"}:
            continue
        key = branch.query.casefold()
        if key in seen_queries:
            continue
        seen_queries.add(key)
        candidates.append({
            "candidate_id": branch.branch_id,
            "query": branch.query,
            "rationale": branch.rationale,
            "origin": "search_plan",
            "branch_id": branch.branch_id,
            "language": branch.language,
            "metrics": branch.metrics,
        })

    for hypothesis in hypothesis_rows:
        for collection_action in hypothesis["collection_needed"]:
            key = collection_action.casefold()
            if not key or key in seen_queries:
                continue
            seen_queries.add(key)
            candidates.append({
                "candidate_id": _stable_id("next", hypothesis["hypothesis_id"], collection_action),
                "query": collection_action,
                "rationale": f"Collection need for hypothesis: {hypothesis['hypothesis']}",
                "origin": "hypothesis_collection_need",
                "hypothesis_ids": [hypothesis["hypothesis_id"]],
                "language": "",
                "metrics": None,
            })

    weights = {
        "uncovered_scope_match": 0.25,
        "hypothesis_discrimination": 0.30,
        "observed_novelty": 0.15,
        "observed_relevance": 0.15,
        "observed_source_diversity": 0.10,
        "observed_duplicate_avoidance": 0.05,
    }


    scored: list[dict[str, Any]] = []
    for candidate in candidates:
        query = candidate["query"]
        scope_matches = [
            dimension for dimension in open_dimensions
            if _matching_dimensions(query, {dimension["dimension"]: [dimension["value"]]})
        ]
        scope_score = len(scope_matches) / len(open_dimensions) if open_dimensions else None

        matched_hypotheses: list[str] = list(candidate.get("hypothesis_ids") or [])
        query_tokens = _tokens(query)
        for hypothesis in hypothesis_rows:
            if hypothesis["hypothesis_id"] in matched_hypotheses:
                continue
            action_texts = hypothesis["collection_needed"] + hypothesis["discriminators"]
            for action in action_texts:
                action_tokens = _tokens(action)
                overlap = len(query_tokens & action_tokens) / len(query_tokens | action_tokens) if query_tokens | action_tokens else 0
                if action.casefold() == query.casefold() or overlap >= 0.35:
                    matched_hypotheses.append(hypothesis["hypothesis_id"])
                    break
        hypothesis_score = (
            len(set(matched_hypotheses)) / len(hypothesis_rows) if hypothesis_rows else None
        )

        metrics = candidate.get("metrics")
        components: dict[str, float | None] = {
            "uncovered_scope_match": scope_score,
            "hypothesis_discrimination": hypothesis_score,
            "observed_novelty": None,
            "observed_relevance": None,
            "observed_source_diversity": None,
            "observed_duplicate_avoidance": None,
        }
        if metrics is not None:
            if metrics.relevance_assessed > 0:
                components["observed_relevance"] = min(1.0, max(0.0, metrics.relevance_rate))
            if metrics.relevant > 0:
                components["observed_novelty"] = min(1.0, max(0.0, metrics.novelty_rate))
            if metrics.retrieved > 0 and metrics.distinct_sources > 0:
                components["observed_source_diversity"] = min(1.0, metrics.distinct_sources / 4.0)
            denominator = metrics.unique + metrics.duplicates
            if denominator > 0:
                components["observed_duplicate_avoidance"] = 1.0 - metrics.duplicate_rate

        available_weight = sum(weights[key] for key, value in components.items() if value is not None)
        score = (
            sum(weights[key] * value for key, value in components.items() if value is not None) / available_weight
            if available_weight else 0.0
        )
        scored.append({
            "candidate_id": candidate["candidate_id"],
            "query": query,
            "rationale": candidate["rationale"],
            "origin": candidate["origin"],
            "branch_id": candidate.get("branch_id", ""),
            "language": candidate.get("language", ""),
            "matched_open_scope": scope_matches,
            "hypothesis_ids": sorted(set(matched_hypotheses)),
            "components": components,
            "component_weights": weights,
            "available_weight": round(available_weight, 4),
            "inspectable_priority": round(score, 4),
            "estimated_cost": {"queries": 1, "records_max": int(max_records_per_query)},
            "cost_basis": "One bounded query action; record maximum is analyst-supplied. No runtime, platform, or access estimate is inferred.",
        })

    scored.sort(key=lambda row: (-row["inspectable_priority"], -row["available_weight"], row["query"].casefold()))
    for index, row in enumerate(scored, 1):
        row["rank"] = index

    recommendations = scored[:int(max_queries)]
    return {
        "schema_version": RESEARCH_INTELLIGENCE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "requirement_id": requirement.requirement_id,
        "plan_created_at": plan.created_at,
        "budget": {"max_queries": int(max_queries), "max_records_per_query": int(max_records_per_query)},
        "plan_scope_not_yet_touched_by_completed_branches": open_dimensions,
        "recommendations": recommendations,
        "recommended_next_collection": recommendations[0] if recommendations else None,
        "score_method": {
            "name": "weighted mean of available inspectable components",
            "weights": weights,
            "missing_component_handling": "Unmeasured components are omitted and remaining weights are renormalized; available_weight shows how much evidence supports each priority.",
            "scope_proxy": "Requirement values mentioned by a candidate and absent from completed branches with records; phrase match or token match allowing a terminal English plural s.",
            "hypothesis_proxy": "Explicit collection-needed/discriminator text, matched by exact text or token Jaccard >= 0.35.",
            "source_diversity_proxy": "Observed distinct source count scaled to four sources; source identity independence is not assumed.",
            "guardrails": [
                "Priority is a transparent ranking aid, not a probability or universal research-quality score.",
                "A natural-language collection need is a proposed query; an analyst should edit and approve it before collection.",
                "Accessibility, live yield, and runtime cost are unestimated unless present in observed plan metrics.",
                "No collection is started by this recommendation operation.",
            ],
        },
    }


def apply_next_evidence_recommendation(
    plan: SearchPlan,
    recommendation: dict[str, Any],
    *,
    actor: str = "research optimizer",
) -> str:
    """Append the selected action to plan history and, when needed, add it paused for review."""
    selected = recommendation.get("recommended_next_collection")
    if not isinstance(selected, dict):
        plan.add_event("next_evidence_recommendation", actor=_clean(actor), outcome="no_candidate")
        return ""
    query = _clean(selected.get("query"))
    existing = next((branch for branch in plan.branches if branch.query.casefold() == query.casefold()), None)
    if existing:
        branch_id = existing.branch_id
        proposal_status = "existing_branch"
    else:
        if len(plan.branches) >= plan.policy.max_branches:
            plan.add_event(
                "next_evidence_recommendation",
                actor=_clean(actor),
                outcome="capacity_reached",
                query=query,
                max_branches=plan.policy.max_branches,
            )
            return ""
        branch = SearchBranch(
            query=query,
            rationale=(
                f"Recommended collection action (priority {selected.get('inspectable_priority', 0)}): "
                f"{_clean(selected.get('rationale')) or 'See next-evidence report.'}"
            ),
            origin="generated",
            status="paused",
            search_family="hypothesis_discriminator" if selected.get("origin") == "hypothesis_collection_need" else "recommended",
            generator="inspectable_next_evidence_v1",
            parent_concept=", ".join(selected.get("hypothesis_ids") or []),
        )
        plan.branches.append(branch)
        branch_id = branch.branch_id
        proposal_status = "added_paused_for_review"
    plan.add_event(
        "next_evidence_recommendation",
        actor=_clean(actor) or "research optimizer",
        outcome=proposal_status,
        candidate_id=selected.get("candidate_id", ""),
        branch_id=branch_id,
        query=query,
        priority=selected.get("inspectable_priority"),
        hypothesis_ids=selected.get("hypothesis_ids") or [],
        cost=selected.get("estimated_cost") or {},
        analyst_approval_required=True,
    )
    return branch_id


def _normalized_text(value: str) -> str:
    return " ".join(_WORD.findall(_clean(value).casefold()))


def _character_shingles(value: str, width: int = 7) -> set[str]:
    compact = "".join(_WORD.findall(value))
    if len(compact) < width:
        return {compact} if compact else set()
    return {compact[index:index + width] for index in range(len(compact) - width + 1)}


def build_content_lineage(
    records: Iterable[PostRecord],
    *,
    similarity_threshold: float = 0.82,
    max_common_shingle_share: float = 0.10,
) -> dict[str, Any]:
    """Find exact and near-duplicate text candidates without claiming copying or independence."""
    if not 0.5 <= float(similarity_threshold) <= 1.0:
        raise ValueError("similarity_threshold must be between 0.5 and 1.0.")
    rows: list[dict[str, Any]] = []
    exact: dict[str, list[int]] = defaultdict(list)
    truncated_documents = 0
    for record in records:
        original = _clean(record.original_text)
        translated = _clean(record.translated_text)
        text = original or translated
        if not text:
            continue
        normalized = _normalized_text(text)
        if not normalized:
            continue
        shingle_text = normalized
        if len(shingle_text) > 20000:
            shingle_text = shingle_text[:20000]
            truncated_documents += 1
        row = {
            "record_key": record.record_key or record.canonical_url or record.native_id,
            "platform": _clean(record.platform),
            "canonical_url": _clean(record.canonical_url),
            "source_host": _host(record.canonical_url or record.source_url),
            "published_at": _clean(record.published_at),
            "language": _clean(record.detected_language or record.platform_language),
            "text_basis": "original_text" if original else "translated_text_fallback",
            "text_sha256": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "shingles": _character_shingles(shingle_text),
        }
        exact[row["text_sha256"]].append(len(rows))
        rows.append(row)

    pair_keys: set[tuple[int, int]] = set()
    pair_generation_truncated = False
    max_candidate_pairs = 250000
    for indexes in exact.values():
        if len(indexes) > 1:
            anchor = indexes[0]
            for right in indexes[1:]:
                if len(pair_keys) >= max_candidate_pairs:
                    pair_generation_truncated = True
                    break
                pair_keys.add((anchor, right))
        if pair_generation_truncated:
            break

    postings: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        for shingle in row["shingles"]:
            postings[shingle].append(index)
    common_limit = max(5, min(200, int(len(rows) * min(float(max_common_shingle_share), 0.005))))
    for indexes in postings.values():
        if len(indexes) > common_limit:
            continue
        for offset, left in enumerate(indexes):
            for right in indexes[offset + 1:]:
                pair_keys.add((left, right))
                if len(pair_keys) >= max_candidate_pairs:
                    pair_generation_truncated = True
                    break
            if pair_generation_truncated:
                break
        if pair_generation_truncated:
            break

    pair_edges: list[dict[str, Any]] = []
    for left_index, right_index in sorted(pair_keys):
        left, right = rows[left_index], rows[right_index]
        exact_match = left["text_sha256"] == right["text_sha256"]
        shared = left["shingles"] & right["shingles"]
        union = left["shingles"] | right["shingles"]
        jaccard = len(shared) / len(union) if union else 0.0
        containment = len(shared) / min(len(left["shingles"]), len(right["shingles"])) if shared else 0.0
        similarity = 1.0 if exact_match else max(jaccard, containment)
        if not exact_match and (similarity < similarity_threshold or len(shared) < 4):
            continue
        pair_edges.append({
            "left_record_key": left["record_key"],
            "right_record_key": right["record_key"],
            "similarity": round(similarity, 4),
            "jaccard": round(jaccard, 4),
            "containment": round(containment, 4),
            "match_type": "exact_normalized_text" if exact_match else "near_duplicate_candidate",
            "same_source_host": bool(left["source_host"] and left["source_host"] == right["source_host"]),
            "chronology": "same_time_or_unknown",
        })
        for edge in [pair_edges[-1]]:
            dates = [left["published_at"], right["published_at"]]
            if all(dates) and dates[0] != dates[1]:
                edge["chronology"] = "left_earlier" if dates[0] < dates[1] else "right_earlier"

    parent = list(range(len(rows)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    key_to_index = {row["record_key"]: index for index, row in enumerate(rows)}
    for edge in pair_edges:
        left, right = root(key_to_index[edge["left_record_key"]]), root(key_to_index[edge["right_record_key"]])
        if left != right:
            parent[right] = left
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(rows)):
        groups[root(index)].append(index)

    clusters = []
    for indexes in groups.values():
        if len(indexes) < 2:
            continue
        members = [rows[index] for index in indexes]
        keys = sorted({row["record_key"] for row in members})
        clusters.append({
            "cluster_id": _stable_id("content", *keys),
            "records": [
                {key: row[key] for key in (
                    "record_key", "platform", "canonical_url", "source_host", "published_at", "language", "text_basis", "text_sha256"
                )}
                for row in members
            ],
            "record_count": len(members),
            "distinct_hosts": sorted({row["source_host"] for row in members if row["source_host"]}),
            "interpretation": "Candidate text-similarity group. Distinct URLs, hosts, and platforms do not establish independent information origins.",
        })

    return {
        "schema_version": RESEARCH_INTELLIGENCE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": {
            "normalization": "Unicode-aware alphanumeric normalization, case folding, and whitespace collapse.",
            "similarity": "Character 7-gram Jaccard and containment; candidates are surfaced for analyst review.",
            "translated_text": "Used only when original_text is absent and labeled as a translation fallback.",
            "limits": "Near-duplicate candidate generation is capped at 250,000 pairs and uses a bounded common-shingle index; individual texts are truncated to 20,000 normalized characters for shingling.",
            "guardrails": [
                "Text similarity is not proof of copying, attribution, or a shared source.",
                "Different hosts are not necessarily independent; similar wording can arise independently.",
                "This deterministic method does not perform cross-lingual semantic matching.",
            ],
        },
        "records_with_text": len(rows),
        "candidate_pair_count": len(pair_edges),
        "candidate_pair_generation_truncated": pair_generation_truncated,
        "documents_shingle_truncated": truncated_documents,
        "clusters": sorted(clusters, key=lambda value: value["cluster_id"]),
        "candidate_pairs": pair_edges,
    }


def _observation_evidence_refs(observation: ResearchObservation) -> list[str]:
    refs = list(observation.source_record_keys)
    for item in observation.evidence:
        refs.append(item.url or f"{item.platform}:{item.native_id}")
        if item.media_artifact_id:
            refs.append(f"media:{item.media_artifact_id}#{item.media_locator}")
    return sorted({value for value in refs if value})


def load_entity_aliases(path: str | Path) -> dict[str, list[str]]:
    payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8-sig"))
    raw = payload.get("entities", payload) if isinstance(payload, dict) else None
    if isinstance(raw, dict):
        rows = raw.items()
    elif isinstance(raw, list):
        rows = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            canonical = _clean(item.get("canonical_name") or item.get("name"))
            aliases = item.get("aliases") or []
            if canonical:
                rows.append((canonical, aliases))
    else:
        raise ValueError("Entity alias registry must be a canonical-name mapping or an entities array.")
    result: dict[str, list[str]] = {}
    for canonical, aliases in rows:
        if not _clean(canonical):
            continue
        if not isinstance(aliases, list):
            aliases = [aliases]
        result[_clean(canonical)] = [_clean(value) for value in aliases if _clean(value)]
    return result


def build_temporal_evidence_graph(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment] = (),
    *,
    entity_aliases: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a provenance-carrying entity/event graph without inferring actor-to-actor ties."""
    observation_rows = list(observations)
    assessment_by_id = {item.observation_id: item for item in assessments}
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    normalized_aliases: dict[str, set[str]] = defaultdict(set)
    canonical_labels: dict[str, str] = {}
    for canonical, raw_aliases in (entity_aliases or {}).items():
        canonical_label = _clean(canonical)
        if not canonical_label:
            continue
        canonical_key = " ".join(canonical_label.casefold().split())
        canonical_labels[canonical_key] = canonical_label
        normalized_aliases[canonical_key].add(canonical_key)
        aliases = raw_aliases if isinstance(raw_aliases, list) else [raw_aliases]
        for alias in aliases:
            alias_key = " ".join(_clean(alias).casefold().split())
            if alias_key:
                normalized_aliases[alias_key].add(canonical_key)
    alias_resolution = {
        alias: next(iter(targets)) for alias, targets in normalized_aliases.items() if len(targets) == 1
    }
    ambiguous_aliases = sorted(alias for alias, targets in normalized_aliases.items() if len(targets) > 1)

    for observation in observation_rows:
        event_id = _stable_id("event", observation.observation_id)
        refs = _observation_evidence_refs(observation)
        assessment = assessment_by_id.get(observation.observation_id)
        nodes[event_id] = {
            "node_id": event_id,
            "node_type": "event",
            "label": observation.title or observation.program_name or observation.summary[:120],
            "observation_id": observation.observation_id,
            "observation_type": observation.observation_type,
            "observed_at": observation.observed_at,
            "valid_from": "",
            "valid_to": "",
            "activity_status": observation.activity_status,
            "verification_state": observation.verification_state,
            "assessment_state": assessment.review_state if assessment else "no_assessment",
            "evidence_refs": refs,
            "country": observation.country,
            "city": observation.city,
        }
        entity_mentions: list[tuple[str, str]] = []
        entity_mentions.extend(("institution", value) for value in ([observation.institution_name] if observation.institution_name else []))
        entity_mentions.extend(("program", value) for value in ([observation.program_name] if observation.program_name else []))
        entity_mentions.extend(("actor", value) for value in observation.actors)
        if assessment:
            entity_mentions.extend(("sponsor", value) for value in assessment.sponsor_entities)
            entity_mentions.extend(("host", value) for value in assessment.host_entities)
            entity_mentions.extend(("partner", value) for value in assessment.partner_entities)

        for role, label in entity_mentions:
            clean_label = _clean(label)
            if not clean_label:
                continue
            matched_key = " ".join(clean_label.casefold().split())
            canonical_key = alias_resolution.get(matched_key, matched_key)
            canonical_label = canonical_labels.get(canonical_key, clean_label)
            entity_id = _stable_id("entity", canonical_key)
            entity = nodes.setdefault(entity_id, {
                "node_id": entity_id,
                "node_type": "entity",
                "label": canonical_label,
                "normalized_key": canonical_key,
                "roles": [],
                "observation_ids": [],
                "evidence_refs": [],
                "observed_names": [],
                "identity_basis": "human_supplied_alias" if canonical_key != matched_key else "case_and_whitespace_normalization",
            })
            if clean_label not in entity["observed_names"]:
                entity["observed_names"].append(clean_label)
            if role not in entity["roles"]:
                entity["roles"].append(role)
            if observation.observation_id not in entity["observation_ids"]:
                entity["observation_ids"].append(observation.observation_id)
            entity["evidence_refs"] = sorted(set(entity["evidence_refs"]) | set(refs))
            key = (entity_id, event_id, role)
            edge = edges.setdefault(key, {
                "edge_id": _stable_id("edge", *key),
                "source": entity_id,
                "target": event_id,
                "predicate": f"{role}_associated_with_observation",
                "role": role,
                "observed_at": observation.observed_at,
                "valid_from": "",
                "valid_to": "",
                "time_basis": "observation.observed_at; this is not a valid-time interval",
                "evidence_refs": [],
                "observation_verification": observation.verification_state,
                "assessment_review_state": assessment.review_state if assessment else "no_assessment",
            })
            edge["evidence_refs"] = sorted(set(edge["evidence_refs"]) | set(refs))

        if assessment:
            for claim in assessment.claims:
                claim_id = _stable_id("claim", claim.claim_id)
                claim_refs = sorted(set(claim.evidence_refs or refs))
                nodes[claim_id] = {
                    "node_id": claim_id,
                    "node_type": "claim",
                    "label": claim.statement,
                    "claim_type": claim.claim_type,
                    "epistemic_status": claim.epistemic_status,
                    "confidence": claim.confidence,
                    "review_state": claim.review_state,
                    "reviewer": claim.reviewer,
                    "observation_id": observation.observation_id,
                    "observed_at": observation.observed_at,
                    "valid_from": "",
                    "valid_to": "",
                    "evidence_refs": claim_refs,
                }
                edge_key = (claim_id, event_id, "claim")
                edges[edge_key] = {
                    "edge_id": _stable_id("edge", *edge_key),
                    "source": claim_id,
                    "target": event_id,
                    "predicate": "claim_about_observation",
                    "observed_at": observation.observed_at,
                    "valid_from": "",
                    "valid_to": "",
                    "time_basis": "observation timestamp only; relationship validity bounds are not inferred",
                    "evidence_refs": claim_refs,
                    "review_state": claim.review_state,
                }

    for node in nodes.values():
        if node.get("node_type") == "entity":
            node["roles"].sort()
            node["observation_ids"].sort()
            node["observed_names"].sort(key=str.casefold)
    return {
        "schema_version": RESEARCH_INTELLIGENCE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "nodes": sorted(nodes.values(), key=lambda value: value["node_id"]),
        "edges": sorted(edges.values(), key=lambda value: value["edge_id"]),
        "ambiguous_alias_keys_not_merged": ambiguous_aliases,
        "guardrails": [
            "Edges connect named entities to evidence-bearing observations; co-appearance does not imply a direct relationship.",
            "Entity matching folds case and whitespace by default. Only human-supplied, unambiguous aliases are merged; ambiguous aliases remain separate.",
            "Analyst-reviewed claims are retained as evidence-bearing nodes; they are not converted into actor-to-actor edges.",
            "Observed timestamps are retained as reported; no valid-from/valid-to interval is inferred.",
            "Unreviewed, rejected, and AI-triaged records remain labeled and should not be treated as verified facts.",
        ],
    }


def _robustness_metrics(pairs: list[tuple[ResearchObservation, StateAssessment]]) -> dict[str, Any]:
    return {
        "verified_observations": len(pairs),
        "countries": len({item.country.casefold() for item, _ in pairs if item.country}),
        "cities": len({(item.country.casefold(), item.city.casefold()) for item, _ in pairs if item.city}),
        "program_domains": len({value for _, assessment in pairs for value in assessment.program_domains}),
        "strategic_audiences": len({value for _, assessment in pairs for value in assessment.strategic_audiences}),
        "narrative_tags": len({value for _, assessment in pairs for value in assessment.narrative_tags}),
        "sponsor_entities": len({value.casefold() for _, assessment in pairs for value in assessment.sponsor_entities}),
    }


def build_robustness_report(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
) -> dict[str, Any]:
    """Run leave-one-source/facet-out checks on human-verified, brief-eligible observations."""
    observation_rows = list(observations)
    assessment_rows = list(assessments)
    observation_by_id = {item.observation_id: item for item in observation_rows}
    pairs = [
        (observation_by_id[item.observation_id], item)
        for item in assessment_rows
        if item.observation_id in observation_by_id
        and observation_by_id[item.observation_id].verification_state == "human_verified"
        and item.brief_eligible
    ]
    baseline = _robustness_metrics(pairs)

    factors: dict[tuple[str, str], list[tuple[ResearchObservation, StateAssessment]]] = defaultdict(list)
    for observation, assessment in pairs:
        for evidence in observation.evidence:
            if evidence.platform:
                factors[("platform", evidence.platform.casefold())].append((observation, assessment))
            if evidence.source_type:
                factors[("source_type", evidence.source_type.casefold())].append((observation, assessment))
            if evidence.language:
                factors[("language", evidence.language.casefold())].append((observation, assessment))
            host = _host(evidence.url)
            if host:
                factors[("source_host", host)].append((observation, assessment))
            language = _clean(evidence.language).casefold()
            if language:
                factors[("language", language.casefold())].append((observation, assessment))
        for actor in set(observation.actors) | set(assessment.sponsor_entities) | set(assessment.host_entities) | set(assessment.partner_entities):
            if actor:
                factors[("actor", actor.casefold())].append((observation, assessment))
        if assessment.ai_provider or assessment.ai_model or assessment.ai_workflow:
            factors[("assessment_ai_provenance", "ai_derived_or_assisted")].append((observation, assessment))

    results: list[dict[str, Any]] = []
    for (factor_type, value), affected_pairs in sorted(factors.items()):
        affected_ids = {observation.observation_id for observation, _ in affected_pairs}
        if factor_type in {"actor", "assessment_ai_provenance"}:
            retained = [(observation, assessment) for observation, assessment in pairs if observation.observation_id not in affected_ids]
        else:
            retained = []
            for observation, assessment in pairs:
                if observation.observation_id not in affected_ids:
                    retained.append((observation, assessment))
                    continue
                if factor_type == "platform":
                    remaining_refs = [item for item in observation.evidence if item.platform.casefold() != value]
                elif factor_type == "source_type":
                    remaining_refs = [item for item in observation.evidence if item.source_type.casefold() != value]
                elif factor_type == "source_host":
                    remaining_refs = [item for item in observation.evidence if _host(item.url) != value]
                elif factor_type == "language":
                    remaining_refs = [item for item in observation.evidence if item.language.casefold() != value]
                else:
                    remaining_refs = list(observation.evidence)
                # Preserve an observation when another recorded evidence reference remains.
                if remaining_refs:
                    retained.append((observation, assessment))
        metrics = _robustness_metrics(retained)
        delta = {key: metrics[key] - baseline[key] for key in baseline}
        results.append({
            "removed_factor": {"type": factor_type, "value": value},
            "affected_observations": len(affected_ids),
            "retained_observations": len(retained),
            "metrics_after_removal": metrics,
            "delta_from_baseline": delta,
            "sensitivity": "unchanged" if all(change == 0 for change in delta.values()) else "changed",
        })

    return {
        "schema_version": RESEARCH_INTELLIGENCE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "ready" if pairs else "insufficient_verified_evidence",
        "eligibility": "Observation verification_state=human_verified and StateAssessment.brief_eligible=true.",
        "baseline": baseline,
        "leave_one_factor_out": results,
        "guardrails": [
            "This is a corpus sensitivity report, not a confidence score or causal test.",
            "An observation with any remaining recorded evidence reference stays in the source-removal cohort.",
            "Unrecorded source metadata and evidence dependence cannot be tested; no language exclusion is run when language is absent from evidence metadata.",
            "Removing an actor removes observations naming that actor; it tests portfolio dependence, not actor causality.",
            "No broad finding is inferred from these descriptive count and breadth metrics.",
        ],
    }


def save_research_intelligence(payload: dict[str, Any], path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return str(target)
