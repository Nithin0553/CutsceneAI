"""Redacted job-bound character facing ownership review for Studio AI.

The engine report is read-only and must be part of the exact reopened,
source-hash-bound Element 7 native acceptance. Even clean actor/mesh observations
do NOT authorize actor yaw, skeletal root, Sequencer or FBX rotation writes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import studio_element7_readback as readback
import studio_element9_outcome as outcome

KIND = "cutsceneai.studio.character_facing_owner_review"
_FACING = re.compile(r"\b(?:facing|faces?|orientation|direction|looking)\b", re.I)
_CHARACTER = re.compile(r"\b(?:character|guard|actor|hero|npc|person|mesh)\b", re.I)
_UNRELATED = re.compile(
    r"\b(?:camera|lens|fov|cut|shot|audio|sound|material|shader|"
    r"texture|position|placement|offset|translation|physics|cloth|vfx)\b",
    re.I,
)
_REJECTION_CODES = frozenset({
    "SOURCE_BOUND_MESH_APPROVAL_OR_ACTOR_BINDING_MISSING",
    "AMBIGUOUS_NATIVE_CHARACTER_ACTOR",
    "NATIVE_TRACK_OR_ANIMATION_OWNER_NOT_ISOLATED",
})


class CharacterFacingReviewError(ValueError):
    """No independently rechecked source and native ownership evidence."""


def relevant_feedback(message: Any) -> bool:
    return bool(
        isinstance(message, str) and 4 <= len(message) <= 1200
        and _FACING.search(message) and _CHARACTER.search(message)
        and not _UNRELATED.search(message)
        and not any(ord(c) < 32 and c not in "\n\t" for c in message)
    )


def build(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    """Summarize only independently reconstructed acceptance, never raw names."""
    if not isinstance(job, dict):
        raise CharacterFacingReviewError("Missing verified native job.")
    try:
        root, _, canonical, *_ = outcome._context(
            workspace, job.get("job_id"),
        )
        if canonical != job:
            raise CharacterFacingReviewError("Selected character job changed.")
        folders = outcome.discover(root, job["job_id"])
        if not folders:
            return {
                "kind": KIND, "status": "NO_INDEPENDENT_REOPENED_NATIVE_ACCEPTANCE",
                "native_owner_observation_available": False,
                "native_edit_authorized": False,
                "full_cutscene_fidelity_verified": False,
            }
        folder = folders[-1]
        readback.build(root, job["job_id"], folder)
        comparison, _ = readback._safe_json(folder / "comparison.json")
        owner_path = folder / "native-character-facing-ownership.json"
        if not owner_path.exists():
            return {
                "kind": KIND, "status": "NATIVE_CHARACTER_OWNER_NOT_OBSERVED",
                "native_owner_observation_available": False,
                "native_edit_authorized": False,
                "full_cutscene_fidelity_verified": False,
            }
        owner, digest = readback._safe_json(owner_path)
        if comparison.get("native_facing_ownership_sha256") != digest:
            raise CharacterFacingReviewError(
                "Native character owner report does not match Element 7 evidence."
            )
    except CharacterFacingReviewError:
        raise
    except (outcome.OutcomeError, readback.Element7ReadbackError,
            KeyError, ValueError, TypeError, OSError) as exc:
        raise CharacterFacingReviewError(
            "Reopened character ownership evidence is stale or incomplete."
        ) from exc
    characters = owner.get("characters")
    rigs = comparison.get("rig_motion_diagnostics")
    if not isinstance(characters, list) or not isinstance(rigs, list):
        raise CharacterFacingReviewError("Native and source rig inventory incomplete.")
    if len(characters) != len(rigs) or len(characters) > 64:
        raise CharacterFacingReviewError("Native character owner scope differs.")
    by_id = {row.get("entity_id"): row for row in characters
             if isinstance(row, dict)}
    if (len(by_id) != len(characters)
            or set(by_id) != {row.get("entity_id") for row in rigs}):
        raise CharacterFacingReviewError("Character identity is missing or ambiguous.")
    native_candidates = 0
    measured_mismatch = 0
    missing_approval = 0
    native_blocked = 0
    for rig in rigs:
        actor_mesh = rig.get("facing_ownership_diagnostic") or {}
        native = by_id[rig["entity_id"]]
        status = native.get("status")
        blocking = native.get("blocking_reasons")
        if (not isinstance(blocking, list)
                or native.get("native_edit_authorized") is not False
                or native.get("actor_yaw_repair_authorized", False) is not False):
            raise CharacterFacingReviewError(
                "Source/native owner report claims unsupported rotation authority."
            )
        if status == "STATIC_NATIVE_OWNER_CANDIDATE_REQUIRES_SOURCE_PROOF":
            native_candidates += 1
        else:
            native_blocked += 1
        if (actor_mesh.get("diagnostic") in {
            "ACTOR_ALIGNED_MESH_OR_COMPONENT_BASIS_DIFFERS",
            "ACTOR_AND_ANATOMICAL_MESH_ORIENTATION_BOTH_DIFFER",
            "ACTOR_ROTATION_DIFFERS_BUT_MESH_FORWARD_MATCHES",
        }):
            measured_mismatch += 1
        if (_REJECTION_CODES.intersection(blocking)
                or rig.get("anatomical_mesh_forward", {}).get("status")
                == "INCOMPLETE"):
            missing_approval += 1
    return {
        "kind": KIND,
        "status": "REOPENED_CHARACTER_OWNER_DIAGNOSTIC_ONLY",
        "native_owner_observation_available": True,
        "observed_character_count": len(characters),
        "static_native_owner_candidates_without_source_authority": native_candidates,
        "native_owner_blocked_count": native_blocked,
        "independently_measured_character_facing_mismatch_count": measured_mismatch,
        "missing_approved_mesh_basis_or_native_scope_count": missing_approval,
        "native_edit_authorized": False,
        "model_command_authorized": False,
        "source_rest_pose_and_root_motion_calibrated": False,
        "full_cutscene_fidelity_verified": False,
        "next_action": (
            "Read the matching source/mesh/rig and native ownership audit. "
            "A source-approved orientation difference cannot identify a safe "
            "actor, mesh or skeletal-root native writer without additional "
            "native track, rest-pose and post-edit verification."
        ),
    }
