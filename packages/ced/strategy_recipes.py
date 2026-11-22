"""Construct read-only, context-grounded CED strategy recipes.

Recipes describe candidate native strategies and required evidence. They are
not executable programs or permissions. Never treat a CED rule as proof of
fidelity in an unseen project.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from contracts import ContractError, validate_recipe

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}\Z")
_RELATIONS = {
    "parent", "binds", "contains", "uses_asset", "depends_on",
    "evaluates", "contributes_to", "controls", "constrains",
}
_DOMAINS = {
    "camera": "camera", "animation": "skeletal", "rig": "skeletal",
    "character": "skeletal", "audio": "audio", "event": "events",
    "light": "lighting", "material": "material", "texture": "material",
    "transform": "spatial", "relationship": "spatial",
    "timeline": "temporal", "sequence": "temporal",
}


class StrategyRecipeError(ValueError):
    pass


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _token(value: Any) -> str:
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        raise StrategyRecipeError("Recipe contains an invalid semantic or strategy identifier.")
    return value


def from_rule(rule: dict[str, Any], *, origin: str,
              related_semantics: list[dict[str, Any]],
              installed_actions: tuple[str, ...] | list[str],
              verified_case_ids: list[str] | None = None) -> dict[str, Any]:
    """Materialize one bounded candidate recipe from an existing CED rule."""
    if not isinstance(rule, dict) or not isinstance(related_semantics, list):
        raise StrategyRecipeError("Recipe requires a structured registered CED rule.")
    if origin not in {"BASELINE_REGISTERED_UNVERIFIED", "LOCAL_REVIEWED_NATIVE_MAPPING"}:
        raise StrategyRecipeError("Recipe origin must be a known baseline or local review.")
    ced = _token(rule.get("ced"))
    rule_id = _token(rule.get("rule_id"))
    source, target, resolution = rule.get("source"), rule.get("target"), rule.get("resolution")
    if not all(isinstance(obj, dict) for obj in (source, target, resolution)):
        raise StrategyRecipeError("Recipe source, target and resolution are invalid.")
    if source.get("engine") != "unity" or target.get("engine") != "unreal":
        raise StrategyRecipeError("Recipe is not a Unity-to-Unreal conversion rule.")
    resolver = _token(resolution.get("resolver"))
    relations = []
    related = []
    for edge in related_semantics[:32]:
        if not isinstance(edge, dict):
            raise StrategyRecipeError("Malformed CED dependency edge.")
        relation = edge.get("relation")
        other = edge.get("concept")
        if relation in _RELATIONS and isinstance(other, str) and _TOKEN.fullmatch(other):
            if other != ced and other not in related:
                related.append(other)
            if len(relations) < 32:
                relations.append({"from": ced, "relation": relation, "to": other})
    installed = []
    for name in installed_actions:
        if name not in installed:
            installed.append(_token(name))
    if len(installed) > 16:
        raise StrategyRecipeError("Too many native action candidates.")
    evidence = resolution.get("required_evidence") or []
    source_evidence = [
        _token(item) for item in evidence
        if isinstance(item, str) and item.startswith("source.")
    ]
    required_target = [
        _token(item) for item in target.get("capabilities_all", [])
    ]
    domain = _DOMAINS.get(ced.split(".")[0], "semantic")
    recipe = {
        "kind": "cutsceneai.ced.strategy_recipe",
        "schema_version": "1",
        "recipe_id": rule_id,
        "semantic_ids": [ced, *related[:31]],
        "relationships": relations,
        "applicability": {
            "source_engine": "unity",
            "target_engine": "unreal",
            "required_source_evidence": source_evidence[:40],
            "required_target_capabilities": required_target[:40],
            "source_version_prefix": str(source.get("version_prefix") or "")[:48],
            "target_version_prefix": str(target.get("version_prefix") or "")[:48],
        },
        "alternatives": [{
            "strategy_id": rule_id,
            "registered_rule_id": rule_id,
            "required_native_actions": installed,
            "limitations": [
                "Registered native adapter and actual project evidence preflight required",
                "No independent current-project cinematic fidelity established",
            ],
            "verification_domains": [domain, "persistence"]
            if domain != "persistence" else ["persistence"],
        }],
        "provenance": {
            "status": (
                "LOCAL_REVIEWED" if origin == "LOCAL_REVIEWED_NATIVE_MAPPING"
                else "BASELINE_ADVISORY"
            ),
            "source_rulebook_version": "1",
            "review_evidence_sha256": None,
            "reviewer": None,
            "heldout_tested": origin == "LOCAL_REVIEWED_NATIVE_MAPPING",
            "native_execution_verified": False,
        },
        "execution_authorized": False,
        "resolver_reference": resolver,
        "verified_case_ids": [
            value for value in (verified_case_ids or [])[:12]
            if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{24}", value)
        ],
    }
    # The JSON schema fields are the portable recipe. The additional
    # provenance fields above are *runtime-only metadata* and never part of
    # an executable plan or a shareable reviewed release.
    portable = {key: value for key, value in recipe.items()
                if key not in {"execution_authorized", "resolver_reference",
                               "verified_case_ids"}}
    try:
        validate_recipe(portable)
    except ContractError as exc:
        raise StrategyRecipeError("CED strategy recipe contract failed: " + str(exc)) from exc
    recipe["recipe_sha256"] = _digest(portable)
    return recipe
