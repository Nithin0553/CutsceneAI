"""Generic source-to-target actor attachment planning with explicit coverage.

The planner is intentionally pure and does NOT mutate Unreal levels. It
reasons from source entity IDs and an explicit target actor mapping rather
than guessing relationships from names or target proximity.
"""
from __future__ import annotations

from typing import Any


class HierarchyPlanError(ValueError):
    """A hierarchy is ambiguous or cannot be safely planned."""


def plan_actor_hierarchy(csir: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """Describe directly mapped actor-parent edges without changing either engine."""
    entities: dict[str, dict[str, Any]] = {}
    seen_names: set[str] = set()
    mapping_entities = mapping.get("entities", {})
    if not isinstance(mapping_entities, dict):
        raise HierarchyPlanError("Expected mapping.entities object.")

    for entity in csir.get("entities", []):
        identifier = entity.get("entity_id")
        name = entity.get("name")
        if not isinstance(identifier, str) or not identifier or identifier in entities:
            raise HierarchyPlanError("Source entity IDs must be unique and nonempty.")
        if not isinstance(name, str) or not name:
            raise HierarchyPlanError(f"Source entity {identifier} is unnamed.")
        if name in seen_names and name in mapping_entities:
            raise HierarchyPlanError(
                f"Source name {name!r} is ambiguous for name-based target mapping."
            )
        seen_names.add(name)
        entities[identifier] = entity

    # Validate all source relationships before planning: never attempt a cycle.
    for identifier, entity in entities.items():
        parent = entity.get("parent_entity_id")
        if parent is not None and parent != "" and parent not in entities:
            raise HierarchyPlanError(
                f"Entity {identifier} refers to missing source parent {parent}."
            )
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise HierarchyPlanError("Cycle found in source hierarchy.")
        if identifier in visited:
            return
        visiting.add(identifier)
        parent_id = entities[identifier].get("parent_entity_id")
        if parent_id:
            visit(str(parent_id))
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in entities:
        visit(identifier)

    mapped: dict[str, str] = {}
    labels: dict[str, str] = {}
    for identifier, entity in entities.items():
        entry = mapping_entities.get(entity["name"])
        if entry is None:
            continue
        if not isinstance(entry, dict) or not isinstance(entry.get("actor_label"), str):
            raise HierarchyPlanError(
                f"Source {entity['name']} mapping lacks target actor_label."
            )
        label = entry["actor_label"]
        if not label:
            raise HierarchyPlanError(f"Source {entity['name']} has empty actor_label.")
        if label in labels:
            raise HierarchyPlanError(
                f"Two source entities map to one target actor label: {label}."
            )
        labels[label] = identifier
        mapped[identifier] = label

    attach: list[dict[str, str]] = []
    unresolved: list[dict[str, str]] = []
    no_parent: list[dict[str, str]] = []
    for identifier, label in mapped.items():
        entity = entities[identifier]
        parent_id = entity.get("parent_entity_id")
        if not parent_id:
            no_parent.append({"entity_id": identifier, "actor_label": label})
            continue
        parent = entities[str(parent_id)]
        parent_label = mapped.get(str(parent_id))
        if parent_label is None:
            unresolved.append({
                "entity_id": identifier,
                "entity_name": entity["name"],
                "actor_label": label,
                "source_parent_entity_id": str(parent_id),
                "source_parent_name": str(parent["name"]),
                "reason": "SOURCE_PARENT_NOT_MAPPED_AS_ACTOR",
            })
            continue
        attach.append({
            "entity_id": identifier,
            "entity_name": entity["name"],
            "actor_label": label,
            "source_parent_entity_id": str(parent_id),
            "source_parent_name": str(parent["name"]),
            "parent_actor_label": parent_label,
            "attachment_rule": "KEEP_WORLD",
            "socket": "",
        })

    return {
        "schema_version": "0.1.0",
        "kind": "cinetwin.target_hierarchy_plan",
        "cutscene_id": str(csir.get("cutscene_id", "")),
        "mapped_source_entity_count": len(mapped),
        "planned_actor_attachments": sorted(attach, key=lambda x: x["entity_name"]),
        "unresolved_source_parents": sorted(
            unresolved, key=lambda x: x["entity_name"]
        ),
        "mapped_source_roots": sorted(
            no_parent, key=lambda x: x["actor_label"]
        ),
        "notes": [
            "A plan is not proof the existing Unreal level has been attached.",
            "KEEP_WORLD preserves the child's world transform when attached.",
            "Unmapped intermediate hierarchy nodes are NOT silently bypassed.",
            "Applying attachments will be a separate explicitly validated step.",
        ],
    }
