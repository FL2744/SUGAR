from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .observations import ResearchObservation
from .state_schema import StateAssessment, USPresenceSite, stable_state_id
from .utils import atomic_path, atomic_write_text, safe_artifact_stem


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _node_id(node_type: str, label: str, context: str = "") -> str:
    return stable_state_id("node", node_type, label, context)


def build_state_network(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    us_sites: Iterable[USPresenceSite] = (),
    *,
    verified_only: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    observation_map = {row.observation_id: row for row in observations}
    site_map = {row.site_id: row for row in us_sites}
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}

    def add_node(node_id: str, node_type: str, label: str, **properties: Any) -> None:
        if node_id not in nodes:
            nodes[node_id] = {"node_id": node_id, "node_type": node_type, "label": label, **properties}

    def add_edge(
        source: str, target: str, relationship: str, assessment: StateAssessment, observation: ResearchObservation
    ) -> None:
        edge_id = stable_state_id("edge", source, relationship, target, assessment.assessment_id)
        if edge_id in edges:
            return
        evidence_refs = list(observation.source_record_keys)
        evidence_refs.extend(item.url for item in observation.evidence if item.url)
        edges[edge_id] = {
            "edge_id": edge_id,
            "source": source,
            "target": target,
            "relationship": relationship,
            "observation_id": observation.observation_id,
            "assessment_id": assessment.assessment_id,
            "verification_state": assessment.review_state,
            "prc_support": assessment.prc_support.level,
            "country": observation.country,
            "city": observation.city,
            "evidence_refs": json.dumps(sorted(set(evidence_refs)), ensure_ascii=False),
            "primary_source_url": observation.primary_source_url,
        }

    for assessment in assessments:
        observation = observation_map.get(assessment.observation_id)
        if observation is None:
            continue
        if verified_only and not (assessment.brief_eligible and observation.verification_state == "human_verified"):
            continue

        obs_node = _node_id("observation", observation.observation_id)
        add_node(
            obs_node,
            "observation",
            observation.title or observation.summary[:100],
            observation_id=observation.observation_id,
            observation_type=observation.observation_type,
            country=observation.country,
            city=observation.city,
            latitude=observation.latitude,
            longitude=observation.longitude,
            verification_state=assessment.review_state,
            prc_support=assessment.prc_support.level,
            primary_source_url=observation.primary_source_url,
        )

        if observation.institution_name:
            institution = _node_id("institution", observation.institution_name, observation.country)
            add_node(
                institution,
                "institution",
                observation.institution_name,
                country=observation.country,
                city=observation.city,
            )
            add_edge(institution, obs_node, "institution_observed_in", assessment, observation)
        if observation.program_name:
            program = _node_id("program", observation.program_name, observation.country)
            add_node(program, "program", observation.program_name, country=observation.country, city=observation.city)
            add_edge(program, obs_node, "program_observed_in", assessment, observation)

        role_groups = (
            ("sponsor", "sponsors", assessment.sponsor_entities),
            ("host", "hosts", assessment.host_entities),
            ("partner", "partners", assessment.partner_entities),
            ("actor", "participates_in", observation.actors),
        )
        for node_type, relationship, values in role_groups:
            for label in values:
                label = _clean(label)
                if not label:
                    continue
                node = _node_id(node_type, label, observation.country)
                add_node(node, node_type, label, country=observation.country)
                add_edge(node, obs_node, relationship, assessment, observation)

        for audience in assessment.strategic_audiences:
            node = _node_id("audience", audience)
            add_node(node, "audience", audience)
            add_edge(obs_node, node, "targets_audience", assessment, observation)
        for domain in assessment.program_domains:
            node = _node_id("program_domain", domain)
            add_node(node, "program_domain", domain)
            add_edge(obs_node, node, "program_domain", assessment, observation)
        for narrative in assessment.narrative_tags:
            node = _node_id("narrative", narrative)
            add_node(node, "narrative", narrative)
            add_edge(obs_node, node, "expresses_or_advances", assessment, observation)

        if assessment.us_overlap.material and assessment.us_overlap.nearest_site_id:
            site = site_map.get(assessment.us_overlap.nearest_site_id)
            label = site.name if site else assessment.us_overlap.nearest_site_name
            site_node = _node_id("us_presence", assessment.us_overlap.nearest_site_id or label)
            add_node(
                site_node,
                "us_presence",
                label,
                site_id=assessment.us_overlap.nearest_site_id,
                network=site.network if site else assessment.us_overlap.nearest_network,
                country=site.country if site else observation.country,
                city=site.city if site else "",
            )
            add_edge(obs_node, site_node, "overlaps_us_public_diplomacy", assessment, observation)

    return sorted(nodes.values(), key=lambda row: (row["node_type"], row["label"])), sorted(
        edges.values(), key=lambda row: (row["relationship"], row["source"], row["target"])
    )


def save_state_network(
    observations: Iterable[ResearchObservation],
    assessments: Iterable[StateAssessment],
    output_directory: str | Path,
    *,
    us_sites: Iterable[USPresenceSite] = (),
    name: str = "state_network",
    verified_only: bool = True,
) -> list[str]:
    nodes, edges = build_state_network(observations, assessments, us_sites, verified_only=verified_only)
    out_dir = Path(output_directory).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = safe_artifact_stem(name, "state_network")
    nodes_path = out_dir / f"{stem}.nodes.csv"
    edges_path = out_dir / f"{stem}.edges.csv"
    json_path = out_dir / f"{stem}.network.json"

    node_fields = sorted({key for row in nodes for key in row}) or ["node_id", "node_type", "label"]
    edge_fields = sorted({key for row in edges for key in row}) or ["edge_id", "source", "target", "relationship"]
    with atomic_path(nodes_path) as temporary:
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=node_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(nodes)
    with atomic_path(edges_path) as temporary:
        with temporary.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=edge_fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(edges)
    atomic_write_text(
        json_path,
        json.dumps(
            {
                "verified_only": verified_only,
                "nodes": nodes,
                "edges": edges,
                "guardrail": "Typed evidence-backed relationships are not a claim of causal influence unless a separately verified influence claim exists.",
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
    )
    return [str(nodes_path), str(edges_path), str(json_path)]
