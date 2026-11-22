"""Unreal-embedded Python: stdlib-only exact-source Element 3 mutation gate.

The Studio HTTP host performs full CED/JSON-schema rechecks when queuing;
the Unreal worker rechecks immutable source, receipt and observed native
capabilities with NO LangGraph/jsonschema/LLM imports in the editor process.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDIO = str(ROOT / "packages" / "studio")
if STUDIO not in sys.path:
    sys.path.insert(0, STUDIO)

import feature_dispatch
import studio_element_native_execution as approval_policy

HEX = re.compile(r"[a-f0-9]{64}\Z")
ID = re.compile(r"[a-f0-9]{32}\Z")
MAX_BYTES = 64 * 1024 * 1024
CAPABILITIES = frozenset({
    "fbx_asset_import", "sequencer_visibility_track",
    "sequencer_skeletal_animation_track", "cine_camera_actor",
})


class NativeElementGateError(ValueError):
    """Native job lacks exact-source registered action consent."""


def _read(path: Path):
    if (path.is_symlink() or not path.is_file()
            or not 0 < path.stat().st_size <= MAX_BYTES):
        raise NativeElementGateError("Native source/action evidence is unsafe or missing.")
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise NativeElementGateError("Malformed immutable Element 3 evidence.") from exc
    if not isinstance(obj, dict):
        raise NativeElementGateError("Expected a structured native action record.")
    return obj


def _sha(path: Path):
    _read(path)  # Enforce file size, type and symlink restrictions.
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(workspace: Path, job: dict) -> Path:
    ident = job.get("candidate_id")
    if not isinstance(ident, str) or not re.fullmatch(
        r"[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}", ident,
    ):
        raise NativeElementGateError("Invalid native Element 3 candidate identity.")
    root = (workspace / "candidates").resolve()
    candidate = (root / ident).resolve()
    if (candidate.parent != root or not candidate.is_dir()
            or candidate != Path(str(job.get("candidate_dir") or "")).resolve()):
        raise NativeElementGateError("Native job belongs to a different candidate.")
    return candidate


def verify_job(workspace: Path, job: dict, native_inventory: dict) -> tuple[dict, dict]:
    """Reverify full consent before any Unreal modification occurs."""
    candidate = _candidate(workspace, job)
    requested = job.get("element_native_authorization_sha256")
    if not isinstance(requested, str) or not HEX.fullmatch(requested):
        raise NativeElementGateError("Native Element 3 operator consent is missing.")
    pointer = _read(candidate / "element-workflow-active.json")
    workflow_sha = pointer.get("workflow_sha256")
    if (pointer.get("candidate_id") != job["candidate_id"]
            or not isinstance(workflow_sha, str) or not HEX.fullmatch(workflow_sha)):
        raise NativeElementGateError("Active source review pointer is invalid.")
    workflow = _read(candidate / ("element-workflow-" + workflow_sha + ".json"))
    if (workflow.get("workflow_sha256") != workflow_sha
            or workflow_sha != approval_policy.digest({
                k: v for k, v in workflow.items() if k != "workflow_sha256"
            })
            or workflow.get("candidate_id") != job["candidate_id"]
            or workflow.get("native_execution_authorized") is not False
            or workflow.get("full_cutscene_fidelity_verified") is not False):
        raise NativeElementGateError("Source-bound review is tampered or stale.")
    if (workflow["source_file_sha256"] != _sha(Path(job["csir"]))
            or workflow["candidate_mapping_sha256"] != _sha(Path(job["mapping"]))
            or workflow["transfer_plan_sha256"]
            != _sha(candidate / "transfer-plan.json")
            or workflow["target_project_identity_sha256"]
            != hashlib.sha256(str(Path(job["expected_project"]).resolve()).encode()).hexdigest()):
        raise NativeElementGateError("Native job source, mapping, plan or project changed.")
    plan = _read(candidate / "transfer-plan.json")
    csir = _read(Path(job["csir"]))
    if (plan.get("sequence_asset_path") != job.get("sequence_path")
            or plan.get("overwrite_sequence") is True
            or workflow.get("source_csir_sha256") != approval_policy.digest(csir)):
        raise NativeElementGateError("Native source/sequence identity differs from source review.")
    source_plan = workflow.get("element_plan")
    if (not isinstance(source_plan, dict)
            or source_plan.get("source_csir_sha256") != workflow["source_csir_sha256"]
            or source_plan.get("element_plan_sha256") != approval_policy.digest({
                k: v for k, v in source_plan.items() if k != "element_plan_sha256"
            })
            or source_plan.get("no_native_execution_permission") is not True
            or source_plan.get("native_conversion_executed") is not False):
        raise NativeElementGateError("Source per-occurrence inventory cannot be trusted.")
    # The exact location/source semantics are independently checked against
    # the current exported source. This is NOT a blanket CED rule approval.
    source_rows = feature_dispatch._source_rows(csir)
    elements = source_plan.get("elements")
    if (not isinstance(elements, list) or len(elements) != len(source_rows)
            or len(elements) != source_plan.get("source_occurrence_count")):
        raise NativeElementGateError("Native occurrence inventory is incomplete.")
    for index, (row, source_row) in enumerate(zip(elements, source_rows)):
        if (row.get("occurrence_id") != f"E{index:05d}"
                or row.get("source_location") != source_row["source_location"]
                or row.get("source_kind") != source_row["kind"]
                or row.get("ced") not in (
                    source_row["ced"], "unknown.unclassified"
                )):
            raise NativeElementGateError("Native occurrence identity or semantics changed.")
    if (not isinstance(native_inventory, dict)
            or native_inventory.get("available") is not True
            or workflow.get("target_capabilities_observed") is not True):
        raise NativeElementGateError("A fresh real Unreal capability observation is required.")
    observed = native_inventory.get("native_capabilities")
    declared = workflow.get("target_capabilities")
    if (not isinstance(observed, dict) or not isinstance(declared, dict)
            or set(declared) != CAPABILITIES
            or any(type(observed.get(k)) is not bool
                   or declared[k] is not observed[k] for k in CAPABILITIES)):
        raise NativeElementGateError("Unreal capability observation changed before mutation.")
    receipt = _read(candidate / "element-review-ack.json")
    if (receipt.get("candidate_id") != job["candidate_id"]
            or receipt.get("workflow_sha256") != workflow_sha
            or receipt.get("scope") != "INVENTORY_REVIEWED_NO_NATIVE_ACTION_PERMISSION"
            or receipt.get("native_execution_authorized") is not False
            or receipt.get("receipt_sha256") != approval_policy.digest({
                k: v for k, v in receipt.items() if k != "receipt_sha256"
            })):
        raise NativeElementGateError("Exact source review was not acknowledged.")
    manifest = approval_policy.inventory(plan, source_plan)
    permission = _read(candidate / "element-native-approval.json")
    approval_policy.verify_authorization(
        permission, manifest, candidate_id=job["candidate_id"],
        workflow_sha256=workflow_sha,
        transfer_plan_sha256=workflow["transfer_plan_sha256"],
    )
    if permission["authorization_sha256"] != requested:
        raise NativeElementGateError("Submitted native action consent does not match operator grant.")
    return permission, manifest


def record_job(workspace: Path, job: dict, native_inventory: dict) -> dict:
    """Emit only a truthful per-action completed-builder ledger."""
    permission, manifest = verify_job(workspace, job, native_inventory)
    candidate = _candidate(workspace, job)
    job_id = job.get("job_id")
    if not isinstance(job_id, str) or not ID.fullmatch(job_id):
        raise NativeElementGateError("Invalid native job receipt identity.")
    receipt_path = candidate / ("unreal-runtime-receipt-" + job_id + ".json")
    receipt = _read(receipt_path)
    result = approval_policy.receipt(
        permission, manifest, receipt,
        job_id=job_id, native_receipt_sha256=_sha(receipt_path),
    )
    path = candidate / ("element-native-dispatch-" + job_id + ".json")
    if path.exists():
        if _read(path) != result:
            raise NativeElementGateError("Saved native action dispatch was modified.")
    else:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
    return result
