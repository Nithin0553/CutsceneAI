"""Build a privacy-minimal semantic dependency graph from Unity CSIR.

No asset names, file paths, native script sources, serialized property values,
or raw object identifiers leave this service. Every semantic occurrence is
counted, even if detailed model retrieval uses pagination.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

MAX_OCCURRENCES = 30000
MAX_EDGES = 60000
_CED = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}\Z")
_KINDS = ("assets", "entities", "tracks", "relationships")


class SemanticGraphError(ValueError):
    """Invalid or unbounded structural evidence; never silently truncate."""


def _concept(value: Any) -> str:
    return value if isinstance(value, str) and _CED.fullmatch(value) else "unknown.unclassified"


@dataclass(frozen=True)
class SemanticGraph:
    counts: dict[str, int]
    relations: dict[str, list[dict[str, Any]]]
    occurrence_count: int
    edge_count: int
    unresolved_reference_count: int


def analyze(csir: dict[str, Any]) -> SemanticGraph:
    if not isinstance(csir, dict):
        raise SemanticGraphError("CSIR must be a structured source document.")
    counts: Counter[str] = Counter()
    nodes: dict[int, tuple[str, str]] = {}
    by_identifier: dict[str, list[int]] = defaultdict(list)
    edges: list[tuple[int, int, str]] = []
    missing = 0

    def node(kind: str, item: dict[str, Any], identity: str = "") -> int:
        if len(nodes) >= MAX_OCCURRENCES:
            raise SemanticGraphError("Source exceeds the bounded semantic occurrence budget.")
        # Canonical curve semantics live in canonical_semantic in source
        # CSIR, not always in ced_type. Keep graph and per-occurrence
        # planner counts aligned without inventing an unknown curve class.
        semantic = (item.get("canonical_semantic")
                    if kind == "curve" and item.get("canonical_semantic")
                    else item.get("ced_type"))
        concept = _concept(semantic)
        index = len(nodes)
        nodes[index] = (kind, concept)
        counts[concept] += 1
        if identity:
            by_identifier[identity].append(index)
        return index

    def edge(first: int, second: int, label: str) -> None:
        if len(edges) >= MAX_EDGES:
            raise SemanticGraphError("Source exceeds the bounded dependency budget.")
        edges.append((first, second, label))

    def link(first: int, identifier: Any, label: str,
             *, required_kind: str | None = None) -> None:
        nonlocal missing
        if identifier in (None, ""):
            return
        if not isinstance(identifier, str):
            missing += 1
            return
        candidates = [
            value for value in by_identifier.get(identifier, [])
            if required_kind is None or nodes[value][0] == required_kind
        ]
        if len(candidates) != 1:
            missing += 1
        else:
            edge(first, candidates[0], label)

    groups: dict[str, list[dict[str, Any]]] = {}
    for kind in _KINDS:
        rows = csir.get(kind) or []
        if not isinstance(rows, list):
            raise SemanticGraphError("Malformed source semantic inventory: " + kind)
        if any(not isinstance(item, dict) for item in rows):
            raise SemanticGraphError("Malformed semantic occurrence: " + kind)
        groups[kind] = rows

    # Register all top-level entities and assets first so dependency resolution
    # is independent of the order of CSIR objects.
    entities: list[tuple[int, dict[str, Any]]] = []
    for item in groups["assets"]:
        node("asset", item, item.get("asset_id") if isinstance(item.get("asset_id"), str) else "")
    for item in groups["entities"]:
        idx = node("entity", item, item.get("entity_id") if isinstance(item.get("entity_id"), str) else "")
        entities.append((idx, item))
    for idx, item in entities:
        link(idx, item.get("parent_entity_id"), "parent", required_kind="entity")
        link(idx, item.get("asset_id"), "uses_asset", required_kind="asset")

    tracks: list[tuple[int, dict[str, Any]]] = []
    for item in groups["tracks"]:
        idx = node("track", item, item.get("track_id") if isinstance(item.get("track_id"), str) else "")
        tracks.append((idx, item))
    for idx, item in tracks:
        link(idx, item.get("binding_entity_id"), "binds", required_kind="entity")
        sections = item.get("sections") or []
        if not isinstance(sections, list) or any(not isinstance(x, dict) for x in sections):
            raise SemanticGraphError("Malformed Timeline sections.")
        for section in sections:
            section_index = node("section", section)
            edge(idx, section_index, "contains")
            payload = section.get("payload") or {}
            if not isinstance(payload, dict):
                raise SemanticGraphError("Malformed Timeline section payload.")
            animation = payload.get("animation") or {}
            if not isinstance(animation, dict):
                raise SemanticGraphError("Malformed Timeline animation payload.")
            curves = animation.get("curves") or []
            if not isinstance(curves, list) or any(not isinstance(x, dict) for x in curves):
                raise SemanticGraphError("Malformed animation curves.")
            for curve in curves:
                curve_index = node("curve", curve)
                edge(section_index, curve_index, "contains")

    for item in groups["relationships"]:
        node("relationship", item)
        first, second = item.get("source_id"), item.get("target_id")
        if not isinstance(first, str) or not isinstance(second, str):
            missing += 1
            continue
        lhs, rhs = by_identifier.get(first, []), by_identifier.get(second, [])
        if len(lhs) != 1 or len(rhs) != 1:
            missing += 1
            continue
        edge(lhs[0], rhs[0], _concept(item.get("ced_type")))

    adjacency: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    for first, second, relationship in edges:
        left, right = nodes[first][1], nodes[second][1]
        adjacency[left][(relationship, right)] += 1
        adjacency[right][("reverse:" + relationship, left)] += 1
    # No source identifiers are exposed: just semantic categories and
    # graph-edge counts. Never embed raw project-specific names in the prompt.
    relations = {
        concept: [
            {"relation": relation, "concept": neighbor, "count": amount}
            for (relation, neighbor), amount in sorted(
                rows.items(), key=lambda pair: (-pair[1], pair[0])
            )
        ]
        for concept, rows in adjacency.items()
    }
    return SemanticGraph(
        counts=dict(sorted(counts.items())),
        relations=relations,
        occurrence_count=len(nodes),
        edge_count=len(edges),
        unresolved_reference_count=missing,
    )
