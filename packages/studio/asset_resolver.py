"""Deterministic, inspectable project asset/actor mapping suggestions.

Only unique exact normalized names are accepted as automatic *proposals*.
No fuzzy guessing, object spawning, imports, or target asset mutation.
"""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any


def _normalize(name: str) -> str:
    # Normalize obvious editor naming differences, not semantic identities.
    return "".join(re.findall(r"[a-z0-9]+", str(name).casefold()))


def _stem(path: str) -> str:
    # Unreal /Game/.../Asset.Asset -> Asset; strip subobject suffix.
    tail = PurePosixPath(str(path).replace("\\", "/")).name
    return tail.split(".")[0]


def _candidates(source: str, available: list[tuple[str, str]]) -> dict[str, Any]:
    source_key = _normalize(source)
    matches = sorted({
        path for identity, path in available
        if source_key and _normalize(identity) == source_key
    })
    if len(matches) == 1:
        outcome = "EXACT_UNIQUE_PROPOSAL"
    elif matches:
        outcome = "AMBIGUOUS"
    else:
        outcome = "NEEDS_MAPPING_OR_IMPORT"
    return {"status": outcome, "candidates": matches, "auto_applied": False}


def propose(
    csir: dict[str, Any],
    *,
    target_actor_labels: list[str],
    target_asset_paths: list[str],
) -> dict[str, Any]:
    """Create complete suggestions for ALL source entities and asset references."""
    actors = [(label, label) for label in target_actor_labels]
    assets = [(_stem(path), path) for path in target_asset_paths]
    actor_entries = []
    for entity in csir.get("entities", []):
        proposal = _candidates(str(entity.get("name", "")), actors)
        actor_entries.append({
            "entity_id": str(entity.get("entity_id", "")),
            "source_name": str(entity.get("name", "")),
            "ced_type": str(entity.get("ced_type", "")),
            **proposal,
        })
    asset_entries = []
    for asset in csir.get("assets", []):
        proposal = _candidates(str(asset.get("name", "")), assets)
        asset_entries.append({
            "asset_id": str(asset.get("asset_id", "")),
            "source_name": str(asset.get("name", "")),
            **proposal,
        })
    return {
        "kind": "cutsceneai.asset_mapping_suggestions",
        "schema_version": "0.1.0",
        "source_cutscene_id": str(csir.get("cutscene_id", "")),
        "actor_count": len(actor_entries),
        "asset_count": len(asset_entries),
        "actors": actor_entries,
        "assets": asset_entries,
        "automatically_applied": False,
        "notes": [
            "Proposals are candidate labels/paths, not verified asset equivalence.",
            "Rig/animation/media type compatibility must be checked before conversion.",
            "Ambiguous/absent mappings cannot be guessed safely.",
        ],
    }
