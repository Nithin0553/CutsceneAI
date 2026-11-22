"""Element 3 Studio workflow: candidate-bound review and independent readback.

This module integrates the existing five read-only Element 3 phases into the
local Studio. It cannot dispatch or authorize native Unreal/Unity actions.
The original prepared-transfer, worker preflight and user feedback policies
remain the sole native execution authorities.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for package in ("studio", "ced", "cinetwin"):
    path = str(ROOT / "packages" / package)
    if path not in sys.path:
        sys.path.insert(0, path)

import ced_agent_knowledge
import studio_element_cinetwin
import studio_element_investigation
import studio_element_plan
import studio_element_schedule
import studio_element_strategy
from sampling_plan import build_plan

KNOWN_CAPABILITIES = (
    "fbx_asset_import", "sequencer_visibility_track",
    "sequencer_skeletal_animation_track", "cine_camera_actor",
)
CANDIDATE_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z_[a-f0-9]{8}\Z")
HEX = re.compile(r"[a-f0-9]{64}\Z")
PAGE_SIZE = 60
MAX_STORED_REVIEWS = 3
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_CAPTURE_BYTES = 128 * 1024 * 1024


class ElementWorkflowError(ValueError):
    """Candidate identity, review authority or captured evidence is invalid."""


def _digest(value: Any) -> str:
    return studio_element_plan._digest(value)


def _sha_file(path: Path, *, max_bytes: int = MAX_SOURCE_BYTES) -> str:
    if not path.is_file() or path.is_symlink() or not 0 < path.stat().st_size <= max_bytes:
        raise ElementWorkflowError("Source/mapping/observation evidence missing or unsafe.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path: Path, *, limit: int = MAX_SOURCE_BYTES) -> dict[str, Any]:
    _sha_file(path, max_bytes=limit)
    try:
        content = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise ElementWorkflowError("Malformed structured candidate evidence.") from exc
    if not isinstance(content, dict):
        raise ElementWorkflowError("Expected a structured evidence object.")
    return content


def _write_new(path: Path, body: dict[str, Any]) -> None:
    data = json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _atomic(path: Path, body: dict[str, Any]) -> None:
    data = json.dumps(body, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with tmp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _workspace(folder: Path) -> tuple[dict, dict, Path, Path, Path]:
    config_path, candidate_path = folder / "connection.json", folder / "active-candidate.json"
    if not config_path.is_file() or not candidate_path.is_file():
        raise ElementWorkflowError("Connect projects and prepare a candidate first.")
    config, candidate = _read(config_path), _read(candidate_path)
    ident = candidate.get("candidate_id")
    if not isinstance(ident, str) or not CANDIDATE_ID.fullmatch(ident):
        raise ElementWorkflowError("Invalid active candidate identity.")
    root = (folder / "candidates").resolve()
    location = (root / ident).resolve()
    if location.parent != root or not location.is_dir() or location.is_symlink():
        raise ElementWorkflowError("Candidate workspace outside Studio or missing.")
    source_path = Path(str(config.get("csir") or "")).resolve()
    mapping = Path(str(candidate.get("mapping_copy") or "")).resolve()
    plan_path = location / "transfer-plan.json"
    if not mapping.is_file() or not plan_path.is_file():
        raise ElementWorkflowError("Prepared immutable mapping or transfer plan missing.")
    if candidate.get("sequence_path") != _read(plan_path).get("sequence_asset_path", candidate.get("sequence_path")):
        raise ElementWorkflowError("Prepared candidate sequence identity changed.")
    return config, candidate, location, source_path, mapping


def _caps(config: dict, worker: dict) -> tuple[bool, dict[str, bool]]:
    """Only current connected, same-project native observations count."""
    def same_path(a: Any, b: Any) -> bool:
        return (isinstance(a, str) and isinstance(b, str)
                and os.path.normcase(str(Path(a).resolve())) ==
                os.path.normcase(str(Path(b).resolve())))
    connected = (worker.get("connected") is True and
                 same_path(worker.get("project"), config.get("target_project")) and
                 (worker.get("level") == config.get("level_path")
                  or config.get("auto_create_level") is True))
    inventory = worker.get("scene_inventory") if connected else None
    observed = inventory.get("native_capabilities") if isinstance(inventory, dict) else None
    if (not isinstance(observed, dict)
            or any(type(observed.get(name)) is not bool for name in KNOWN_CAPABILITIES)):
        return False, {key: False for key in KNOWN_CAPABILITIES}
    return True, {key: observed[key] for key in KNOWN_CAPABILITIES}


def _knowledge(csir: dict, capabilities: dict, folder: Path, target_version: str) -> dict:
    home = folder.parent
    return ced_agent_knowledge.retrieve_all(
        csir, target_capabilities=capabilities,
        source_version=str(csir.get("source", {}).get("engine_version") or ""),
        target_version=target_version,
        approved_store=home / "ced-knowledge",
        case_store=home / "ced-cases",
        feedback_store=home / "ced-experiences.jsonl",
    )


def _build(folder: Path, caps: dict[str, bool], observed: bool,
           target_version: str = "") -> dict[str, Any]:
    config, candidate, location, csir_path, mapping_path = _workspace(folder)
    csir = _read(csir_path)
    knowledge = _knowledge(csir, caps, folder, target_version)
    plan = studio_element_plan.prepare(csir, knowledge, caps)
    schedule = studio_element_schedule.build(plan, csir)
    strategy = studio_element_strategy.build(plan, schedule, knowledge, csir, caps)
    investigation = studio_element_investigation.build(
        plan, schedule, strategy, knowledge, csir, caps,
    )
    report = {
        "kind": "cutsceneai.studio.element_workflow",
        "schema_version": "1",
        "candidate_id": candidate["candidate_id"],
        "source_file_sha256": _sha_file(csir_path),
        "source_csir_sha256": plan["source_csir_sha256"],
        "candidate_mapping_sha256": _sha_file(mapping_path),
        "transfer_plan_sha256": _sha_file(location / "transfer-plan.json"),
        "target_project_identity_sha256": hashlib.sha256(str(
            Path(config["target_project"]).resolve()
        ).encode("utf-8")).hexdigest(),
        "target_capabilities_observed": observed,
        "target_capabilities": caps,
        "target_version": target_version,
        "knowledge_sha256": knowledge["knowledge_sha256"],
        "element_plan": plan,
        "element_schedule": schedule,
        "element_strategy": strategy,
        "element_investigation": investigation,
        "native_execution_authorized": False,
        "full_cutscene_fidelity_verified": False,
    }
    report["workflow_sha256"] = _digest(report)
    return report


def _active(folder: Path) -> dict[str, Any]:
    _config, _candidate, location, _source, _mapping = _workspace(folder)
    pointer_path = location / "element-workflow-active.json"
    if not pointer_path.is_file():
        raise ElementWorkflowError("No Element 3 review yet. Prepare it first.")
    pointer = _read(pointer_path)
    digest = pointer.get("workflow_sha256")
    if (not isinstance(digest, str) or not HEX.fullmatch(digest)
            or pointer.get("candidate_id") != _candidate["candidate_id"]):
        raise ElementWorkflowError("Candidate element workflow pointer was altered.")
    path = location / ("element-workflow-" + digest + ".json")
    report = _read(path)
    if (report.get("workflow_sha256") != digest
            or _digest({k: v for k, v in report.items()
                        if k != "workflow_sha256"}) != digest):
        raise ElementWorkflowError("Candidate element workflow checksum is invalid.")
    expected = _build(
        folder, report["target_capabilities"],
        report["target_capabilities_observed"], report["target_version"],
    )
    if expected != report:
        raise ElementWorkflowError(
            "Candidate Element 3 review is stale or modified. Prepare a fresh review."
        )
    return report


def _review_ack(location: Path, digest: str) -> bool:
    file = location / "element-review-ack.json"
    if not file.is_file():
        return False
    value = _read(file)
    return (value.get("kind") == "cutsceneai.studio.element_review_ack"
            and value.get("workflow_sha256") == digest
            and value.get("scope") == "INVENTORY_REVIEWED_NO_NATIVE_ACTION_PERMISSION"
            and value.get("native_execution_authorized") is False
            and value.get("receipt_sha256") == _digest({
                k: v for k, v in value.items() if k != "receipt_sha256"
            }))


def _case_rows(report: dict) -> list[dict]:
    plan = report["element_plan"]["elements"]
    nodes = {row["occurrence_id"]: row for row in report["element_schedule"]["nodes"]}
    strategy = {row["occurrence_id"]: row
                for row in report["element_strategy"]["comparisons"]}
    investigations = {row["occurrence_id"]: row
                      for row in report["element_investigation"]["findings"]}
    return [{
        "occurrence_id": row["occurrence_id"],
        "source_kind": row["source_kind"],
        "source_location": row["source_location"],
        "ced": strategy[row["occurrence_id"]]["ced"],
        "source_state": row["state"],
        "schedule_status": nodes[row["occurrence_id"]]["status"],
        "suggested_action": strategy[row["occurrence_id"]]["suggested_action"],
        "eligible_alternatives": [item["action"] for item in
            strategy[row["occurrence_id"]]["alternatives"]
            if item["eligible_for_model_proposal"] is True],
        "investigation_status": investigations[row["occurrence_id"]]["state"],
        "reason_codes": investigations[row["occurrence_id"]]["reason_codes"],
        "required_evidence": investigations[row["occurrence_id"]]["required_evidence"],
        "next_steps": investigations[row["occurrence_id"]]["available_investigation_steps"],
        "native_verified": False,
    } for row in plan]


def _index(folder: Path, report: dict) -> dict:
    _config, _candidate, location, _source, _mapping = _workspace(folder)
    file = location / "element-readback-index.json"
    if not file.exists():
        return {"kind": "cutsceneai.studio.element_readback_index",
                "candidate_id": report["candidate_id"],
                "workflow_sha256": report["workflow_sha256"],
                "observations": []}
    index = _read(file)
    digest = index.get("index_sha256")
    if (index.get("kind") != "cutsceneai.studio.element_readback_index"
            or index.get("candidate_id") != report["candidate_id"]
            or index.get("workflow_sha256") != report["workflow_sha256"]
            or not isinstance(index.get("observations"), list)
            or len(index["observations"]) > MAX_STORED_REVIEWS
            or digest != _digest({k: v for k, v in index.items()
                                  if k != "index_sha256"})):
        raise ElementWorkflowError("Saved CineTwin evidence index is stale or tampered.")
    return index


def _readback_inputs(folder: Path, report: dict, index: dict):
    config, _candidate, location, csir_path, _mapping = _workspace(folder)
    csir = _read(csir_path)
    capture_path = Path(str(config.get("capture") or ""))
    if not config.get("capture"):
        raise ElementWorkflowError("Real Unity source CineTwin behavior capture required.")
    source_capture = _read(capture_path, limit=MAX_CAPTURE_BYTES)
    sampling = build_plan(csir, csir_sha256=_sha_file(csir_path))
    recorded = []
    for item in index["observations"]:
        if (not isinstance(item, dict)
                or not isinstance(item.get("sha256"), str)
                or not HEX.fullmatch(item["sha256"])
                or not isinstance(item.get("path"), str)):
            raise ElementWorkflowError("Saved target observation record is malformed.")
        path = Path(item["path"]).resolve()
        if _sha_file(path, max_bytes=MAX_CAPTURE_BYTES) != item["sha256"]:
            raise ElementWorkflowError("Previously reviewed target observation changed.")
        captured = _read(path, limit=MAX_CAPTURE_BYTES)
        recorded.append(captured)
    return csir, source_capture, sampling, recorded


def _current_native_status(report: dict, config: dict, worker: dict) -> bool:
    observed, caps = _caps(config, worker)
    return (observed == report["target_capabilities_observed"]
            and caps == report["target_capabilities"])


def _preview(report: dict, folder: Path, worker: dict,
             *, offset: int = 0) -> dict[str, Any]:
    if type(offset) is not int or offset < 0 or offset > studio_element_plan.MAX_OCCURRENCES:
        raise ElementWorkflowError("Invalid element review page offset.")
    config, _candidate, location, _source, _mapping = _workspace(folder)
    rows = _case_rows(report)
    selected = rows[offset: offset + PAGE_SIZE]
    index = _index(folder, report)
    latest = None
    if index["observations"]:
        csir, source_capture, sampling, target_captures = _readback_inputs(
            folder, report, index,
        )
        if len(target_captures) == 1:
            saved = studio_element_cinetwin.build(
                csir, report["element_plan"], sampling, source_capture, target_captures[0],
            )
        else:
            saved = studio_element_cinetwin.remeasure(
                csir, report["element_plan"], sampling, source_capture, target_captures,
            )
        last_digest = index["observations"][-1]["report_sha256"]
        actual = (saved["attribution_sha256"] if len(target_captures) == 1
                  else saved["remeasurement_sha256"])
        if actual != last_digest:
            raise ElementWorkflowError("Saved CineTwin report does not match fresh evidence.")
        latest = {
            "status": "MEASURED_DOMAINS_ONLY_FIDELITY_NOT_ESTABLISHED",
            "observation_count": len(target_captures),
            "report_sha256": actual,
            "remeasurement_attempts": len(target_captures) - 1,
            "next_attempt_recommended": (
                saved["next_attempt_recommended"]
                if len(target_captures) > 1 else False
            ),
            "per_occurrence": (
                saved["per_occurrence"][offset:offset + PAGE_SIZE]
                if len(target_captures) > 1 else
                saved["occurrences"][offset:offset + PAGE_SIZE]
            ),
            "native_repair_authorized": False,
            "full_cutscene_fidelity_verified": False,
        }
    return {
        "available": True,
        "kind": "cutsceneai.studio.element_workflow_summary",
        "candidate_id": report["candidate_id"],
        "workflow_sha256": report["workflow_sha256"],
        "source_occurrence_count": len(rows),
        "offset": offset,
        "page_size": PAGE_SIZE,
        "has_more": offset + PAGE_SIZE < len(rows),
        "source_state_counts": dict(sorted(Counter(row["source_state"] for row in rows).items())),
        "schedule_status_counts": dict(sorted(Counter(row["schedule_status"] for row in rows).items())),
        "investigation_state_counts": dict(sorted(
            Counter(row["investigation_status"] for row in rows).items()
        )),
        "target_capabilities_observed": report["target_capabilities_observed"],
        "target_capability_evidence_current": _current_native_status(report, config, worker),
        "review_acknowledged": _review_ack(location, report["workflow_sha256"]),
        "native_execution_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "elements": selected,
        "verification": latest,
    }


def prepare(folder: Path, worker: dict) -> dict[str, Any]:
    config, _candidate, location, _source, _mapping = _workspace(folder)
    observed, caps = _caps(config, worker)
    version = (str(worker.get("engine_version") or "")[:48] if observed else "")
    report = _build(folder, caps, observed, version)
    digest = report["workflow_sha256"]
    file = location / ("element-workflow-" + digest + ".json")
    if not file.exists():
        _write_new(file, report)
    elif _read(file) != report:
        raise ElementWorkflowError("Existing candidate Element 3 snapshot was modified.")
    pointer = {"candidate_id": report["candidate_id"], "workflow_sha256": digest}
    _atomic(location / "element-workflow-active.json", pointer)
    # An old acknowledgment or readback from another snapshot never carries
    # forward to the new capability/knowledge/source binding.
    return _preview(report, folder, worker)


def current(folder: Path, worker: dict, *, offset: int = 0) -> dict[str, Any]:
    try:
        report = _active(folder)
    except ElementWorkflowError as exc:
        if str(exc).startswith("No Element 3 review yet"):
            return {"available": False, "status": "NOT_PREPARED",
                    "native_execution_authorized": False}
        raise
    return _preview(report, folder, worker, offset=offset)


def acknowledge(folder: Path, worker: dict, workflow_sha256: str) -> dict:
    report = _active(folder)
    config, _candidate, location, _source, _mapping = _workspace(folder)
    if (not isinstance(workflow_sha256, str)
            or workflow_sha256 != report["workflow_sha256"]
            or not _current_native_status(report, config, worker)):
        raise ElementWorkflowError(
            "Element review or native capability evidence changed; prepare and review again."
        )
    receipt = {
        "kind": "cutsceneai.studio.element_review_ack",
        "candidate_id": report["candidate_id"],
        "workflow_sha256": report["workflow_sha256"],
        "scope": "INVENTORY_REVIEWED_NO_NATIVE_ACTION_PERMISSION",
        "native_execution_authorized": False,
    }
    receipt["receipt_sha256"] = _digest(receipt)
    _atomic(location / "element-review-ack.json", receipt)
    return {"acknowledged": True, "candidate_id": report["candidate_id"],
            "native_execution_authorized": False}


def require_acknowledgment(folder: Path, worker: dict, candidate_id: str) -> None:
    _config, _candidate, location, _source, _mapping = _workspace(folder)
    if _candidate["candidate_id"] != candidate_id:
        raise ElementWorkflowError("Element review belongs to a different candidate.")
    if not (location / "element-workflow-active.json").is_file():
        # The original manual/automated transfer remains backward compatible
        # when an Element 3 review was never requested.
        return
    report = _active(folder)
    config, _candidate, location, _source, _mapping = _workspace(folder)
    if (not _review_ack(location, report["workflow_sha256"])
            or not _current_native_status(report, config, worker)):
        raise ElementWorkflowError(
            "Review and acknowledge the current source-bound Element 3 issues "
            "before native generation. This does not approve unregistered actions."
        )


def verify_target(folder: Path, worker: dict, target_path: str) -> dict:
    report = _active(folder)
    _config, _candidate, location, _source, _mapping = _workspace(folder)
    if not isinstance(target_path, str) or not target_path.strip():
        raise ElementWorkflowError("Choose an existing Unreal CineTwin target JSON.")
    target_file = Path(target_path).expanduser().resolve()
    target_digest = _sha_file(target_file, max_bytes=MAX_CAPTURE_BYTES)
    index = _index(folder, report)
    if (len(index["observations"]) >= MAX_STORED_REVIEWS
            or any(item["sha256"] == target_digest for item in index["observations"])):
        raise ElementWorkflowError(
            "Duplicate observation or two-remeasurement budget reached."
        )
    csir, source_capture, sampling, prior = _readback_inputs(folder, report, index)
    target = _read(target_file, limit=MAX_CAPTURE_BYTES)
    # A declared, different target candidate sequence cannot be accepted as
    # this candidate's result. A missing native sequence remains unverified.
    observed = target.get("target") if isinstance(target.get("target"), dict) else {}
    declared = observed.get("sequence_asset_path")
    if declared and declared != _candidate["sequence_path"]:
        raise ElementWorkflowError("Target native sequence differs from active candidate.")
    captures = [*prior, target]
    if len(captures) == 1:
        result = studio_element_cinetwin.build(
            csir, report["element_plan"], sampling, source_capture, target,
        )
        field = "attribution_sha256"
    else:
        result = studio_element_cinetwin.remeasure(
            csir, report["element_plan"], sampling, source_capture, captures,
        )
        field = "remeasurement_sha256"
    digest = result[field]
    filename = location / ("element-readback-" + digest + ".json")
    if not filename.exists():
        _write_new(filename, result)
    elif _read(filename) != result:
        raise ElementWorkflowError("Previously saved CineTwin readback is corrupted.")
    index["observations"].append({
        "path": str(target_file),
        "sha256": target_digest,
        "report_sha256": digest,
    })
    index.pop("index_sha256", None)
    index["index_sha256"] = _digest(index)
    _atomic(location / "element-readback-index.json", index)
    return _preview(report, folder, worker)
