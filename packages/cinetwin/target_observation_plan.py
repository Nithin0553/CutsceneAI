"""Pure-Python CineTwin target observer planning.

A project mapping may contain a subset of source entities. Never silently
pretend that unbound source entities have been observed in the target.
"""
from __future__ import annotations

import math
from typing import Any


class TargetPlanError(ValueError):
    pass


def prepare_observation(
    sampling_plan: dict[str, Any],
    mapping: dict[str, Any],
    *,
    max_samples: int | None = None,
) -> dict[str, Any]:
    if sampling_plan.get("kind") != "cinetwin.sampling_plan":
        raise TargetPlanError("Expected CineTwin source sampling plan.")
    if max_samples is not None and max_samples < 1:
        raise TargetPlanError("max_samples must be positive.")
    source_entities = sampling_plan.get("entities", [])
    all_times = [
        float(item["time_seconds"]) for item in sampling_plan.get("samples", [])
    ]
    if not all_times or any(not math.isfinite(t) for t in all_times):
        raise TargetPlanError("Missing or invalid source sample times.")
    if any(b <= a for a, b in zip(all_times, all_times[1:])):
        raise TargetPlanError("Sample times must be strictly increasing.")

    by_name = mapping.get("entities", {})
    bound: list[dict[str, str]] = []
    missing: list[dict[str, str]] = []
    labels: set[str] = set()
    for entity in source_entities:
        name = str(entity.get("name", ""))
        entity_id = str(entity.get("entity_id", ""))
        item = by_name.get(name)
        if isinstance(item, dict) and item.get("actor_label"):
            label = str(item["actor_label"])
            if label in labels:
                raise TargetPlanError(
                    "Multiple source entities map to same actor label: " + label
                )
            labels.add(label)
            bound.append({
                "entity_id": entity_id,
                "source_name": name,
                "actor_label": label,
                "ced_type": str(entity.get("ced_type", "")),
            })
        else:
            missing.append({"entity_id": entity_id, "source_name": name})
    rig_ids = {str(x) for x in sampling_plan.get("skeletal_entity_ids", [])}
    resolved_rigs = [entry for entry in bound if entry["entity_id"] in rig_ids]
    missing_rigs = sorted(rig_ids - {x["entity_id"] for x in resolved_rigs})
    if missing_rigs:
        raise TargetPlanError(
            "Cannot observe animated source rigs without target actor mappings: "
            + ", ".join(missing_rigs)
        )

    selected_times = all_times if max_samples is None else all_times[:max_samples]
    return {
        "cutscene_id": sampling_plan["cutscene_id"],
        "source": sampling_plan["source"],
        "full_sample_count": len(all_times),
        "selected_times_seconds": selected_times,
        "bound": bound,
        "missing": missing,
        "skeletal_rigs": resolved_rigs,
    }
