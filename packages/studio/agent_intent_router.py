"""Ground natural-language CutSceneAI corrections in registered, measured capabilities.

This module is a *decision boundary*, not an Unreal executor. It recognizes
user intent conservatively, reports what evidence is missing, and only exposes
an already implemented, allowlisted strategy when its existing native readback
and source-provenance gates pass. Adapter catalog entries are informational:
registration never gives an LLM permission to run commands.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

MAX_FEEDBACK = 1200
MAX_CATALOG = 24
MAX_ISSUES = 30
# These are understanding hints, not a source of native execution authority.
_DOMAIN_CUES = (
    ("shader", r"\b(?:shader|shaders|hlsl|shadergraph|shader[ -]graph|urp|hdrp)\b"),
    ("material", r"\b(?:texture|textures|textured|material|materials|albedo|"
                 r"base[ -]?colou?r|roughness|metallic|checkerboard|pink[ -]?surface)\b"),
    ("camera", r"\b(?:camera|cameras|lens|fov|framing|shot|cinematography|"
               r"depth[ -]of[ -]field|focus|zoom|pan|dolly)\b"),
    ("lighting", r"\b(?:light|lights|lighting|shadow|shadows|exposure|"
                 r"illuminat\w*|too[ -]dark|too[ -]bright)\b"),
    ("rigging", r"\b(?:retarget\w*|rig|rigs|skeleton|skeletal|bone|bones|"
                r"skin\w*|joint|joints|morph|blendshape)\b"),
    ("animation", r"\b(?:animat\w*|walking|walks|running|runs|turn\w*|"
                 r"facing|face[sd]?|pose|poses|motion|moving|mov\w*|"
                 r"drift\w*|foot|feet|root[ -]motion)\b"),
    ("physics", r"\b(?:physics|collision|collider|collide\w*|rigidbody|"
               r"rigid[ -]body|trigger[ -]volume|hitbox|gravity|ragdoll|"
               r"bounce|bouncing|constraint|cloth)\b"),
    ("vfx", r"\b(?:vfx|particle|particles|niagara|smoke|fire|flames|"
           r"explosion|spark|sparks|emitter|procedural[ -]effect)\b"),
    ("audio", r"\b(?:audio|sound|sounds|voice|voices|dialogue|music|"
             r"speech|speak\w*|lip[ -]sync)\b"),
    ("events", r"\b(?:signal|signals|callback|callbacks|event|events|"
              r"timeline[ -]marker|activation)\b"),
    ("plugin", r"\b(?:plugin|plugins|middleware|unity[ -]script|"
              r"custom[ -]component|mono\s?behaviour|package|sdk)\b"),
    ("transform", r"\b(?:position|placement|location|orientation|rotation|"
                 r"scale|offset|floating|alignment|translate|trajectory)\b"),
)
_COMPILED = tuple((domain, re.compile(pattern, re.IGNORECASE))
                  for domain, pattern in _DOMAIN_CUES)
_ENVIRONMENT = re.compile(
    r"\b(?:wall|floor|ground|ceiling|door|window|tree|rock|sky|"
    r"terrain|environment|building|hallway|room|prop|scenery)\b",
    re.IGNORECASE,
)
_CHARACTER = re.compile(
    r"\b(?:character|guard|person|actor|hero|npc|body|skeleton|"
    r"face|hand|hands|foot|feet|arm|legs?)\b",
    re.IGNORECASE,
)
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,95}\Z")


class IntentError(ValueError):
    """Bad or unbounded feedback/capability evidence."""


def recognize(message: str | None) -> dict[str, Any]:
    """Categorize the user's words without guessing an actual scene object.

    No parsed token, name, number or instruction from this function is ever
    executable. Ambiguous multi-domain requests stay diagnostic-only.
    """
    if message is None or message == "":
        return {
            "mode": "automatic_diagnosis", "domains": [],
            "target_scope": "unspecified", "ambiguous": False,
            "source_object_verified": False,
        }
    if (not isinstance(message, str) or len(message) > MAX_FEEDBACK
            or len(message.strip()) < 4 or any(
                ord(char) < 32 and char not in "\n\t" for char in message
            )):
        raise IntentError("Correction text is malformed or exceeds safe limits.")
    domains = [
        domain for domain, pattern in _COMPILED if pattern.search(message)
    ]
    # A rig/retarget issue is a specific type of skeletal animation. Keep
    # both labels for explanations but never permit an unrelated material fix.
    if "rigging" in domains and "animation" in domains:
        domains.remove("animation")
    scope_character = bool(_CHARACTER.search(message))
    scope_environment = bool(_ENVIRONMENT.search(message))
    scope = ("conflicting" if scope_character and scope_environment else
             "character" if scope_character else
             "environment" if scope_environment else "unspecified")
    return {
        "mode": "user_feedback", "domains": domains,
        "target_scope": scope,
        "ambiguous": len(domains) != 1 or scope == "conflicting",
        "source_object_verified": False,
    }


def _sanitized_adapters(catalog: object) -> list[dict[str, Any]]:
    """Surface informative identifiers, never arbitrary adapter code or paths."""
    if not isinstance(catalog, list):
        return []
    safe = []
    seen = set()
    for item in catalog[:MAX_CATALOG]:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("adapter_id") or item.get("adapter_name") or "")
        source_type = str(item.get("source_type") or "")
        if not _IDENTIFIER.fullmatch(name) or (
            source_type and not _IDENTIFIER.fullmatch(source_type)
        ) or name in seen:
            continue
        seen.add(name)
        safe.append({
            "adapter_id": name,
            "source_type": source_type,
            "registered_only": True,
            "approved_for_agent_execution": False,
            "native_fidelity_verified": False,
        })
    return safe


def route(
    message: str | None,
    *,
    generation_complete: bool,
    native_material_fallback_slots: int,
    source_albedo_provenance: bool,
    completed_repairs: int,
    repair_budget: int,
    independent_issues: object,
    adapter_catalog: object = None,
    fallback_observation_scope: str = "character",
    transform_repair_evidence: dict[str, Any] | None = None,
    camera_lens_repair_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Choose *admissible strategies*, not a repair or an engine operation.

    A model selects only within these strategies; the existing native
    executor still checks source GUIDs, exact job identity, save/receipt
    consistency and no-overwrite. No amount of catalog metadata alone can
    make an unimplemented strategy executable.
    """
    intent = recognize(message)
    if (type(generation_complete) is not bool
            or type(source_albedo_provenance) is not bool
            or type(native_material_fallback_slots) is not int
            or native_material_fallback_slots < 0
            or type(completed_repairs) is not int or completed_repairs < 0
            or type(repair_budget) is not int or repair_budget <= 0
            or not isinstance(independent_issues, list)
            or fallback_observation_scope not in {"character", "global"}):
        raise IntentError("Native provenance or repair budget is malformed.")
    if len(independent_issues) > 500 or any(
        not isinstance(item, Mapping) for item in independent_issues
    ):
        raise IntentError("Invalid independent diagnostics supplied to agent.")
    observed = []
    for item in independent_issues[:MAX_ISSUES]:
        category = str(item.get("category") or "")
        if _IDENTIFIER.fullmatch(category):
            observed.append(category)
    scope = intent["target_scope"]
    domains = intent["domains"]
    user_is_material_only = (
        intent["mode"] == "user_feedback"
        and domains == ["material"]
        and not intent["ambiguous"]
        and (scope in {"unspecified", "character"} or
             (scope == "environment" and fallback_observation_scope == "global"))
    )
    auto_mode = intent["mode"] == "automatic_diagnosis"
    eligibility = bool(
        generation_complete and native_material_fallback_slots > 0
        and source_albedo_provenance
        and completed_repairs < repair_budget
        and (auto_mode or user_is_material_only)
    )
    transform_eligible = bool(
        intent["mode"] == "user_feedback"
        and domains == ["transform"] and not intent["ambiguous"]
        and generation_complete and completed_repairs < repair_budget
        and isinstance(transform_repair_evidence, dict)
        and transform_repair_evidence.get("eligible") is True
        and isinstance(transform_repair_evidence.get("entity"), str)
    )
    camera_eligible = bool(
        intent["mode"] == "user_feedback"
        and domains == ["camera"] and not intent["ambiguous"]
        and generation_complete and completed_repairs < repair_budget
        and isinstance(camera_lens_repair_evidence, dict)
        and camera_lens_repair_evidence.get("eligible") is True
        and camera_lens_repair_evidence.get("kind")
        == "cutsceneai.studio.static_camera_lens_review"
        and isinstance(camera_lens_repair_evidence.get("camera_repair_sha256"), str)
    )
    if camera_eligible:
        disposition = "GUARDED_STATIC_CAMERA_LENS_REPAIR_AVAILABLE"
        reason = (
            "An exact-source, single native CineCamera has an independently "
            "measured constant vertical FOV mismatch and no planned camera "
            "FOV animation. The editor must independently recheck the "
            "current component/Sequencer key ownership before a single "
            "user-authorized, rollback-protected focal-length edit."
        )
        allowed = ["report_only", "restore_static_camera_lens"]
    elif transform_eligible:
        disposition = "GUARDED_ACTOR_TRANSLATION_AVAILABLE"
        reason = ("The exact user-named character has an independently sampled "
                  "constant actor/root offset, without conflicting native transform "
                  "tracks. Unreal must remeasure and validate before any edit.")
        allowed = ["report_only", "restore_constant_actor_offset"]
    elif eligibility:
        disposition = "GUARDED_MATERIAL_REPAIR_AVAILABLE"
        reason = ("A source-backed material fallback was observed in native "
                  "Unreal readback. A bounded, previously installed repair "
                  "may be evaluated; the result must be re-audited.")
        allowed = ["report_only", "restore_source_albedo"]
    elif intent["ambiguous"] and not auto_mode:
        disposition = "AMBIGUOUS_OR_MULTI_DOMAIN_REPORT"
        reason = ("The request is ambiguous or spans multiple semantic "
                  "domains. Do not apply unrelated automatic edits.")
        allowed = ["report_only"]
    elif completed_repairs >= repair_budget:
        disposition = "REPAIR_BUDGET_EXHAUSTED"
        reason = "The authorized repair budget is exhausted; do not replay edits."
        allowed = ["report_only"]
    elif not generation_complete:
        disposition = "NO_SAFE_GENERATED_TARGET"
        reason = "A generated, saved target sequence is required before native corrections."
        allowed = ["report_only"]
    elif domains and "material" not in domains:
        disposition = "REGISTERED_REPAIR_REQUIRED"
        reason = ("No executable and independently verified agent repair is "
                  "registered for the requested semantic domain.")
        allowed = ["report_only"]
    elif scope == "environment" and fallback_observation_scope == "character":
        disposition = "TARGET_SCOPE_EVIDENCE_MISMATCH"
        reason = ("Only character fallback slots were independently observed; "
                  "they cannot justify an environment/material correction.")
        allowed = ["report_only"]
    elif native_material_fallback_slots <= 0:
        disposition = "MISMATCH_NOT_INDEPENDENTLY_OBSERVED"
        reason = ("The requested fix has no independently observed native "
                  "fallback evidence. User feedback remains unverified.")
        allowed = ["report_only"]
    elif not source_albedo_provenance:
        disposition = "SOURCE_PROVENANCE_REQUIRED"
        reason = "No verified source texture provenance is available for the proposed repair."
        allowed = ["report_only"]
    else:
        disposition = "NO_VERIFIED_STRATEGY"
        reason = "The request cannot be matched to a supported, source-backed native repair."
        allowed = ["report_only"]
    return {
        "schema_version": "0.1.0",
        "intent": intent,
        "disposition": disposition,
        "reason": reason,
        "independent_issue_categories": observed,
        "native_material_fallback_slots": native_material_fallback_slots,
        "registered_adapters_informational": _sanitized_adapters(adapter_catalog),
        "safe_strategies": allowed,
        "requires_editor_receipt": (
            eligibility or transform_eligible or camera_eligible
        ),
        "user_observation_verified": False,
        "native_fidelity_verified": False,
        "model_can_authorize_native_commands": False,
        "model_can_install_adapters": False,
    }
