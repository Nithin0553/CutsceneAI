"""Source-bound per-occurrence conversion candidates for the AI agent.

Only existing registered Unreal builder actions can be suggested. A model
selection is advisory: it NEVER modifies the native transfer plan, grants
adapter permission, or constitutes observed conversion/fidelity success.
Every occurrence, including unknown scripts/curves/assets, is accounted for.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

PACKAGES = Path(__file__).resolve().parents[1]
STUDIO = str(PACKAGES / "studio")
if STUDIO not in sys.path:
    sys.path.insert(0, STUDIO)
import feature_dispatch

MAX_OCCURRENCES = 30000
MAX_MODEL_OCCURRENCES = 256
MODEL_BATCH_SIZE = 12
_SEMANTIC = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{0,127}\Z")
_ACTION_CAPABILITY = {
    "camera_setup": "cine_camera_actor",
    "camera_cut": "cine_camera_actor",
    "camera_fov": "cine_camera_actor",
    "skeletal_animation": "sequencer_skeletal_animation_track",
    "actor_visibility": "sequencer_visibility_track",
}


class ElementPlanError(ValueError):
    """An element plan cannot be grounded in this exact source and CED snapshot."""


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _rows(csir: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(csir, dict):
        raise ElementPlanError("Per-occurrence planning requires Unity CSIR.")
    collected: list[dict[str, Any]] = []

    def group(name: str) -> list[dict[str, Any]]:
        items = csir.get(name, [])
        if not isinstance(items, list) or any(not isinstance(v, dict) for v in items):
            raise ElementPlanError("Malformed source occurrence collection: " + name)
        return items

    def add(kind: str, location: str, item: dict[str, Any], raw_id: Any,
            *, owner: str = "") -> None:
        if len(collected) >= MAX_OCCURRENCES:
            raise ElementPlanError("Source exceeds supported element planning budget.")
        semantic = (item.get("canonical_semantic") if kind == "curves"
                    and item.get("canonical_semantic") else item.get("ced_type"))
        collected.append({
            "kind": kind, "source_location": location,
            "raw_id": raw_id if isinstance(raw_id, str) and raw_id else None,
            "semantic": semantic,
            "owner": owner, "item": item,
        })

    for i, item in enumerate(group("assets")):
        add("assets", f"assets[{i}]", item, item.get("asset_id"))
    for i, item in enumerate(group("entities")):
        add("entities", f"entities[{i}]", item, item.get("entity_id"))
    for i, item in enumerate(group("tracks")):
        track = f"tracks[{i}]"
        add("tracks", track, item, item.get("track_id"))
        sections = item.get("sections", [])
        if not isinstance(sections, list) or any(not isinstance(v, dict) for v in sections):
            raise ElementPlanError("Malformed Timeline section inventory.")
        for j, section in enumerate(sections):
            location = f"{track}.sections[{j}]"
            add("sections", location, section, section.get("section_id"), owner=track)
            payload = section.get("payload") or {}
            if not isinstance(payload, dict):
                raise ElementPlanError("Malformed Timeline section payload.")
            animation = payload.get("animation") or {}
            if not isinstance(animation, dict):
                raise ElementPlanError("Malformed Timeline animation payload.")
            curves = animation.get("curves") or []
            if not isinstance(curves, list) or any(not isinstance(v, dict) for v in curves):
                raise ElementPlanError("Malformed Timeline animation curves.")
            for k, curve in enumerate(curves):
                add("curves", f"{location}.payload.animation.curves[{k}]",
                    curve, curve.get("curve_id"), owner=location)
    for i, item in enumerate(group("relationships")):
        add("relationships", f"relationships[{i}]", item, item.get("relationship_id"))
    return collected


def prepare(csir: dict[str, Any], knowledge: dict[str, Any],
            target_capabilities: dict[str, Any]) -> dict[str, Any]:
    """Construct a complete immutable baseline using source and CED evidence.

    The decision vocabulary is restricted to explicit builder actions, not
    the far broader category-level CED coverage or similarity suggestions.
    """
    if (not isinstance(knowledge, dict) or knowledge.get("retrieval_complete") is not True
            or knowledge.get("no_native_write_permission") is not True
            or not isinstance(knowledge.get("knowledge_sha256"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", knowledge["knowledge_sha256"])
            or not isinstance(knowledge.get("entries"), list)
            or not isinstance(knowledge.get("coverage_ledger"), list)
            or not isinstance(target_capabilities, dict)
            or any(not isinstance(k, str) or type(v) is not bool
                   for k, v in target_capabilities.items())):
        raise ElementPlanError("Complete, read-only CED and observed target capabilities required.")
    rows = _rows(csir)
    if len(rows) != knowledge.get("source_occurrence_count"):
        raise ElementPlanError("CED and source per-occurrence inventories disagree.")
    by_ced = {}
    for entry in knowledge["entries"]:
        ced = entry.get("ced") if isinstance(entry, dict) else None
        if not isinstance(ced, str) or ced in by_ced:
            raise ElementPlanError("CED knowledge has duplicated or invalid concepts.")
        by_ced[ced] = entry
    known = {ced for ced, row in by_ced.items() if row.get("semantic_known") is True}
    canonical = {row["ced"]: row["source_occurrences"] for row in knowledge["coverage_ledger"]}
    observed: dict[str, int] = defaultdict(int)
    for row in rows:
        semantic = row["semantic"]
        token = semantic if isinstance(semantic, str) and _SEMANTIC.fullmatch(semantic) else "unknown.unclassified"
        observed[token] += 1
    if dict(observed) != canonical:
        raise ElementPlanError("CED semantic coverage ledger disagrees with source occurrences.")

    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    any_index: dict[str, list[str]] = defaultdict(list)
    by_location = {row["source_location"]: f"E{i:05d}" for i, row in enumerate(rows)}
    for row in rows:
        if row["raw_id"] is not None and row["kind"] in {"assets", "entities", "tracks"}:
            ident = by_location[row["source_location"]]
            index[(row["kind"], row["raw_id"])].append(ident)
            any_index[row["raw_id"]].append(ident)

    def dependency(label: str, source_id: Any, candidates: list[str],
                   target: list[str], missing: list[str]) -> None:
        if source_id in (None, ""):
            return
        if len(candidates) == 1:
            target.append(candidates[0])
        else:
            missing.append(label + "_MISSING_OR_AMBIGUOUS")

    elements = []
    for i, row in enumerate(rows):
        kind, item = row["kind"], row["item"]
        source = row["semantic"]
        ced = source if isinstance(source, str) and _SEMANTIC.fullmatch(source) else "unknown.unclassified"
        entry = by_ced.get(ced)
        dependencies: list[str] = []
        missing: list[str] = []
        if row["owner"]:
            dependencies.append(by_location[row["owner"]])
        if kind == "entities":
            parent = item.get("parent_entity_id")
            dependency("parent", parent, index.get(("entities", parent), []),
                       dependencies, missing)
            asset = item.get("asset_id")
            dependency("asset", asset, index.get(("assets", asset), []),
                       dependencies, missing)
        elif kind == "tracks":
            bound = item.get("binding_entity_id")
            dependency("binding", bound, index.get(("entities", bound), []),
                       dependencies, missing)
        elif kind == "relationships":
            for label, field in (("source", "source_id"), ("target", "target_id")):
                raw = item.get(field)
                dependency(label, raw, any_index.get(raw, []) if isinstance(raw, str)
                           else [], dependencies, missing)
        valid_semantic = ced in known
        advertised = list(feature_dispatch.EXPLICIT_ACTIONS.get(ced, ())) if valid_semantic else []
        grounded = set(entry.get("native_action_candidates", [])) if entry else set()
        if not grounded.issubset(feature_dispatch.BUILDER_ACTIONS):
            raise ElementPlanError("CED offered a native action not registered with Unreal.")
        actions = []
        absent_caps = []
        for action in advertised:
            if action not in feature_dispatch.BUILDER_ACTIONS or action not in grounded:
                continue
            required = _ACTION_CAPABILITY.get(action)
            if required is not None and target_capabilities.get(required) is False:
                absent_caps.append(required)
                continue
            actions.append(action)
        if missing:
            actions = []
            state = "UNRESOLVED_SOURCE_DEPENDENCY"
        elif not valid_semantic:
            state = "UNKNOWN_SEMANTIC_INVESTIGATE"
        elif entry is None:
            state = "CED_KNOWLEDGE_MISSING"
        elif actions:
            state = "NATIVE_ACTION_CANDIDATES_REQUIRE_PREFLIGHT"
        elif absent_caps:
            state = "TARGET_CAPABILITY_MISSING"
        else:
            state = "NO_REGISTERED_NATIVE_ACTION"
        elements.append({
            "occurrence_id": f"E{i:05d}",
            "source_location": row["source_location"],
            "source_kind": kind,
            "ced": ced if valid_semantic else "unknown.unclassified",
            "dependencies": list(dict.fromkeys(dependencies)),
            "unresolved_dependencies": missing,
            "candidate_actions": sorted(set(actions)),
            "missing_target_capabilities": sorted(set(absent_caps)),
            "state": state,
            "selected_action": "report_only",
            "model_reviewed": False,
        })
    result = {
        "kind": "cutsceneai.studio.element_conversion_plan",
        "schema_version": "1",
        "source_csir_sha256": _digest(csir),
        "ced_knowledge_sha256": knowledge["knowledge_sha256"],
        "target_capabilities_sha256": _digest(target_capabilities),
        "source_occurrence_count": len(elements),
        "model_reviewed_count": 0,
        "no_native_execution_permission": True,
        "native_conversion_executed": False,
        "elements": elements,
    }
    result["element_plan_sha256"] = _digest(result)
    return result


def apply_choices(plan: dict[str, Any], choices: list[dict[str, Any]],
                  *, expected_ids: list[str]) -> dict[str, Any]:
    """Validate one complete model batch; reject omissions or invented actions."""
    if (not isinstance(plan, dict) or not isinstance(choices, list)
            or not isinstance(expected_ids, list)
            or len(choices) != len(expected_ids)
            or len(set(expected_ids)) != len(expected_ids)):
        raise ElementPlanError("Element AI choices must cover the exact requested batch.")
    items = plan.get("elements")
    if not isinstance(items, list) or plan.get("no_native_execution_permission") is not True:
        raise ElementPlanError("Element plan has no validated advisory authority.")
    expected = set(expected_ids)
    candidates = {row["occurrence_id"]: row for row in items}
    if not expected <= candidates.keys():
        raise ElementPlanError("Agent referred to a nonexistent source occurrence.")
    selected = {}
    for row in choices:
        if not isinstance(row, dict) or set(row) != {"occurrence_id", "action"}:
            raise ElementPlanError("Model returned unregistered element choice fields.")
        ident, action = row["occurrence_id"], row["action"]
        if ident not in expected or ident in selected:
            raise ElementPlanError("Model duplicated or invented a source occurrence.")
        item = candidates[ident]
        if action != "report_only" and action not in item["candidate_actions"]:
            raise ElementPlanError("Model selected an unregistered or unsupported native action.")
        if item["model_reviewed"]:
            raise ElementPlanError("Source element cannot be reviewed twice.")
        selected[ident] = action
    if set(selected) != expected:
        raise ElementPlanError("Model silently omitted one or more source occurrences.")
    updated = json.loads(json.dumps(plan))
    for row in updated["elements"]:
        if row["occurrence_id"] in selected:
            row["selected_action"] = selected[row["occurrence_id"]]
            row["model_reviewed"] = True
    updated["model_reviewed_count"] = sum(bool(row["model_reviewed"])
                                          for row in updated["elements"])
    updated.pop("element_plan_sha256", None)
    updated["element_plan_sha256"] = _digest(updated)
    return updated


def verify(plan: dict[str, Any], csir: dict[str, Any],
           knowledge: dict[str, Any],
           target_capabilities: dict[str, Any]) -> None:
    """Independently recompute all source/knowledge/action predicates."""
    baseline = prepare(csir, knowledge, target_capabilities)
    if not isinstance(plan, dict) or set(plan) != set(baseline):
        raise ElementPlanError("Element plan contains unknown or missing contract fields.")
    checksum = plan.get("element_plan_sha256")
    if (not isinstance(checksum, str)
            or checksum != _digest({k: v for k, v in plan.items()
                                   if k != "element_plan_sha256"})):
        raise ElementPlanError("Element plan evidence digest is invalid.")
    fixed = {"kind", "schema_version", "source_csir_sha256",
             "ced_knowledge_sha256", "target_capabilities_sha256",
             "source_occurrence_count", "no_native_execution_permission",
             "native_conversion_executed"}
    if any(plan[key] != baseline[key] for key in fixed):
        raise ElementPlanError("Element plan belongs to stale or foreign source evidence.")
    if (not isinstance(plan.get("elements"), list)
            or len(plan["elements"]) != len(baseline["elements"])):
        raise ElementPlanError("Element plan lost source occurrences.")
    count = 0
    for actual, expected in zip(plan["elements"], baseline["elements"]):
        if (not isinstance(actual, dict) or set(actual) != set(expected)
                or any(actual[k] != expected[k] for k in expected
                       if k not in {"selected_action", "model_reviewed"})):
            raise ElementPlanError("An occurrence has changed its source or registered action evidence.")
        if type(actual["model_reviewed"]) is not bool:
            raise ElementPlanError("Invalid element model review flag.")
        if (actual["selected_action"] != "report_only"
                and (not actual["model_reviewed"]
                     or actual["selected_action"] not in expected["candidate_actions"])):
            raise ElementPlanError("An AI choice bypassed a registered native action guard.")
        count += actual["model_reviewed"]
    if type(plan.get("model_reviewed_count")) is not int or count != plan["model_reviewed_count"]:
        raise ElementPlanError("Element review count is inconsistent with exact source coverage.")



def review_with_model(plan: dict[str, Any], *,
                      provider: Any) -> tuple[dict[str, Any], list[str]]:
    """Ask the configured AI to select an advisory action for EACH occurrence.

    No raw Unity identifiers, component values or paths cross this API.
    Full occurrence coverage and exact response membership are enforced for
    every bounded request; model failures do not authorize native fallback.
    """
    if not isinstance(plan, dict) or plan.get("no_native_execution_permission") is not True:
        raise ElementPlanError("Untrusted per-element plan cannot be sent to a model.")
    source = plan.get("elements")
    if not isinstance(source, list) or len(source) != plan.get("source_occurrence_count"):
        raise ElementPlanError("Element plan lost occurrence inventory.")
    if len(source) > MAX_MODEL_OCCURRENCES:
        raise ElementPlanError(
            "The selected cutscene exceeds the bounded per-element AI review "
            "budget. Every element remains inventoried, but no native AI "
            "submission is allowed until planning is paged durably."
        )
    if not callable(getattr(provider, "complete_json", None)):
        raise ElementPlanError("Per-element planning requires a configured JSON model.")
    output = plan
    response_hashes: list[str] = []
    for position in range(0, len(source), MODEL_BATCH_SIZE):
        batch = source[position:position + MODEL_BATCH_SIZE]
        payload = {
            "source_occurrence_count": len(source),
            "page_index": position // MODEL_BATCH_SIZE,
            "elements": [{
                "occurrence_id": item["occurrence_id"],
                "ced": item["ced"],
                "source_kind": item["source_kind"],
                "state": item["state"],
                "dependencies": item["dependencies"],
                "unresolved_dependencies": item["unresolved_dependencies"],
                "candidate_actions": item["candidate_actions"],
                "missing_target_capabilities": item["missing_target_capabilities"],
            } for item in batch],
        }
        result = provider.complete_json(
            task="cutsceneai_element_conversion_choices",
            instructions=(
                "You are a read-only Unity-to-Unreal cinematic conversion "
                "planner. For EACH source occurrence, choose exactly one "
                "registered candidate native action or report_only. The "
                "options are only conversion candidates; actual native "
                "preflight, mapping and fidelity verification have not "
                "happened. Choose report_only for unknown semantics, absent "
                "actions, missing dependencies or uncertain feasibility. "
                "Do not invent APIs, identifiers, code, project assets, "
                "pathnames, conversions or execution results. Return only "
                "the exact structured JSON choices."
            ),
            payload=payload,
            schema={
                "type": "object", "additionalProperties": False,
                "properties": {
                    "choices": {
                        "type": "array",
                        "items": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "occurrence_id": {"type": "string"},
                                "action": {"type": "string"},
                            },
                            "required": ["occurrence_id", "action"],
                        },
                    },
                },
                "required": ["choices"],
            },
        )
        answer = getattr(result, "answer", None)
        if not isinstance(answer, dict) or set(answer) != {"choices"}:
            raise ElementPlanError("AI element review returned invalid top-level data.")
        output = apply_choices(
            output, answer["choices"],
            expected_ids=[item["occurrence_id"] for item in batch],
        )
        digest = getattr(result, "response_sha256", None)
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ElementPlanError("Agent element response is missing a bounded evidence digest.")
        response_hashes.append(digest)
    if output["model_reviewed_count"] != len(source):
        raise ElementPlanError("AI model omitted part of the source cutscene.")
    return output, response_hashes
