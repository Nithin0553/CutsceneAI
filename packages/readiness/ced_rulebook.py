"""Versioned CED rulebook: catalog, proposals and evidence-gated reuse.

CED remains the engine-neutral taxonomy. An entry does NOT imply an executable
native conversion. This module never executes untrusted adapter code, mutates
Unity/Unreal projects, or promotes learned/user rules without recorded
independent evidence and human review.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

CONTRACTS = Path(__file__).resolve().parents[1] / "contracts" / "dictionary"
TAXONOMY = CONTRACTS / "cutscene-elements-v0.2.json"
BASE_RULES = CONTRACTS / "adaptive-rules-v0.1.json"
RULEBOOK = CONTRACTS / "ced-mapping-rulebook-v1.json"
VERSION = "1"
_HASH = re.compile(r"^[a-f0-9]{64}$")
_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_SELECTOR_KEYS = {"engine", "version_prefix", "capabilities_all", "settings_equals"}
_RULE_KEYS = {"rule_id", "ced", "priority", "source", "target", "resolution", "notes"}
_RESOLUTION_KEYS = {"outcome", "resolver", "parameters", "required_evidence"}
_OUTCOMES = {"EXACT", "CONVERTED", "RETARGETED", "BAKED",
             "RECONSTRUCTED", "TARGET_MAPPED", "BLOCKED"}


class CEDRulebookError(ValueError):
    """Untrusted mapping, stale review or conflicting learned rule."""


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _read(path: Path, *, max_bytes: int = 2 * 1024 * 1024) -> dict:
    if (path.is_symlink() or any(parent.is_symlink() for parent in path.parents)
            or not path.is_file() or not 0 < path.stat().st_size <= max_bytes):
        raise CEDRulebookError("CED rulebook evidence is missing, symlinked or oversized.")
    try:
        result = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise CEDRulebookError("Invalid CED rulebook JSON.") from exc
    if not isinstance(result, dict):
        raise CEDRulebookError("Expected CED rulebook JSON object.")
    return result


def _paths(store: str | Path):
    root = Path(store)
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise CEDRulebookError("CED rulebook store cannot follow symlinks.")
    return root, root / "candidates", root / "approvals", root / "native_evidence"


def _validate_selector(value: Any, engine: str) -> None:
    if (not isinstance(value, dict) or set(value) - _SELECTOR_KEYS
            or value.get("engine") != engine):
        raise CEDRulebookError("Candidate must explicitly bind Unity-to-Unreal engine direction.")
    if "version_prefix" in value and (
            not isinstance(value["version_prefix"], str)
            or not re.fullmatch(r"[0-9A-Za-z._-]{1,40}", value["version_prefix"])):
        raise CEDRulebookError("Invalid engine version selector.")
    capabilities = value.get("capabilities_all", [])
    if (not isinstance(capabilities, list)
            or len(capabilities) > 32
            or any(not isinstance(x, str) or not _TOKEN.fullmatch(x)
                   for x in capabilities)
            or len(set(capabilities)) != len(capabilities)):
        raise CEDRulebookError("Invalid candidate capability selectors.")
    settings = value.get("settings_equals", {})
    if (not isinstance(settings, dict) or len(settings) > 16
            or any(not isinstance(k, str) or not _TOKEN.fullmatch(k)
                   for k in settings)
            or len(_bytes(settings)) > 2048):
        raise CEDRulebookError("Invalid project settings selector.")


def validate_candidate(rule: Any) -> dict:
    """Check data shape; this alone does not authorize native use."""
    if not isinstance(rule, dict) or set(rule) - _RULE_KEYS:
        raise CEDRulebookError("Mapping candidate has unknown or unsafe fields.")
    rule_id, ced = rule.get("rule_id"), rule.get("ced")
    if (not isinstance(rule_id, str) or not _TOKEN.fullmatch(rule_id)
            or not isinstance(ced, str) or not _TOKEN.fullmatch(ced)
            or "." not in ced):
        raise CEDRulebookError("Mapping candidate needs stable rule and CED identifiers.")
    if type(rule.get("priority", 0)) is not int or not -1000 <= rule.get("priority", 0) <= 1000:
        raise CEDRulebookError("Mapping priority is outside the bounded range.")
    _validate_selector(rule.get("source"), "unity")
    _validate_selector(rule.get("target"), "unreal")
    resolution = rule.get("resolution")
    if (not isinstance(resolution, dict) or set(resolution) - _RESOLUTION_KEYS
            or resolution.get("outcome") not in _OUTCOMES
            or not isinstance(resolution.get("resolver"), str)
            or not _TOKEN.fullmatch(resolution["resolver"])):
        raise CEDRulebookError("Missing or invalid conversion resolution.")
    requirements = resolution.get("required_evidence", [])
    if (not isinstance(requirements, list) or not requirements
            or len(requirements) > 32
            or len(set(requirements)) != len(requirements)
            or any(not isinstance(x, str)
                   or not x.startswith(("source.", "target.", "transfer."))
                   or not _TOKEN.fullmatch(x) for x in requirements)):
        raise CEDRulebookError("Candidate needs explicit source/target evidence requirements.")
    parameters = resolution.get("parameters", {})
    if not isinstance(parameters, dict) or len(_bytes(parameters)) > 4096:
        raise CEDRulebookError("Candidate parameters exceed bounded declarative data.")
    if "notes" in rule and (
            not isinstance(rule["notes"], str) or len(rule["notes"]) > 1000):
        raise CEDRulebookError("Candidate notes exceed the privacy-safe length limit.")
    if len(_bytes(rule)) > 8192:
        raise CEDRulebookError("Mapping candidate exceeds supported size.")
    return rule


def _concepts() -> set[str]:
    taxonomy = _read(TAXONOMY)
    groups = taxonomy.get("categories")
    if not isinstance(groups, dict):
        raise CEDRulebookError("CED taxonomy lacks semantic categories.")
    rows = [item for values in groups.values() for item in values]
    if not rows or any(not isinstance(x, str) for x in rows):
        raise CEDRulebookError("Invalid CED taxonomy concepts.")
    return set(rows)


def _baseline() -> list[dict]:
    values = _read(BASE_RULES).get("rules")
    if not isinstance(values, list):
        raise CEDRulebookError("Missing baseline adaptive rules.")
    return values


def coverage(approved: list[dict] | None = None) -> dict[str, Any]:
    """Inventory *every* CED concept, including unmapped and unsupported."""
    configuration = _read(RULEBOOK)
    if configuration.get("schema_version") != VERSION:
        raise CEDRulebookError("Unexpected CED rulebook contract version.")
    concepts = _concepts()
    rules = _baseline() + (approved or [])
    active = {row["ced"] for row in rules if row.get("ced") in concepts}
    return {
        "kind": "cutsceneai.ced.rulebook_coverage", "schema_version": VERSION,
        "total_concepts": len(concepts), "concepts_with_candidate_rules": len(active),
        "unmapped_concepts": len(concepts - active),
        "concepts": [
            {"ced": concept, "mapping_status": (
                "RULE_REGISTERED_NATIVE_FIDELITY_NOT_IMPLIED"
                if concept in active else "UNMAPPED_REQUIRES_CANDIDATE")}
            for concept in sorted(concepts)
        ],
    }


def propose(store: str | Path, rule: dict, *, origin: str,
            feature_sha256: str) -> str:
    """Persist a user/test/training proposal, never a production mapping."""
    validate_candidate(rule)
    if origin not in {"USER", "TESTING", "TRAINING"}:
        raise CEDRulebookError("Unknown rule proposal origin.")
    if not isinstance(feature_sha256, str) or not _HASH.fullmatch(feature_sha256):
        raise CEDRulebookError("Proposal requires a stable, nonprivate feature SHA256.")
    root, candidates, approvals, evidence = _paths(store)
    for folder in (root, candidates, approvals, evidence):
        folder.mkdir(exist_ok=True)
    value = {"kind": "cutsceneai.ced.rule_candidate", "schema_version": VERSION,
             "origin": origin, "feature_sha256": feature_sha256,
             "rule": rule, "status": "PROPOSED_NOT_EXECUTABLE"}
    candidate_id = _digest(value)
    path = candidates / (candidate_id + ".json")
    if path.exists():
        if _read(path) != {**value, "candidate_id": candidate_id}:
            raise CEDRulebookError("Existing candidate identity is inconsistent.")
        return candidate_id
    if path.is_symlink():
        raise CEDRulebookError("Refusing symlinked candidate storage.")
    with path.open("x", encoding="utf-8") as handle:
        json.dump({**value, "candidate_id": candidate_id}, handle,
                  sort_keys=True, allow_nan=False)
        handle.write("\n")
    return candidate_id


def _candidate(store: Path, candidate_id: str) -> dict:
    if not isinstance(candidate_id, str) or not _HASH.fullmatch(candidate_id):
        raise CEDRulebookError("Malformed candidate ID.")
    item = _read(store / "candidates" / (candidate_id + ".json"))
    payload = {key: value for key, value in item.items() if key != "candidate_id"}
    if (item.get("candidate_id") != candidate_id or _digest(payload) != candidate_id
            or item.get("kind") != "cutsceneai.ced.rule_candidate"
            or item.get("schema_version") != VERSION
            or item.get("status") != "PROPOSED_NOT_EXECUTABLE"):
        raise CEDRulebookError("Candidate content or ID has been tampered.")
    validate_candidate(item.get("rule"))
    return item


def _eligible_adapter(rule: dict) -> bool:
    """Only registered baseline resolver+parameter+evidence contracts execute.

    Adding a *new* resolver requires an implementation, review and regression
    tests in the source tree. LLM-authored Python/Blueprint is never loaded.
    """
    for baseline in _baseline():
        br, rr = baseline.get("resolution", {}), rule["resolution"]
        if (br.get("resolver") == rr["resolver"]
                and br.get("outcome") == rr["outcome"]
                and br.get("parameters", {}) == rr.get("parameters", {})
                and set(br.get("required_evidence", [])) <= set(rr["required_evidence"])
                and set(baseline.get("source", {}).get("capabilities_all", []))
                    <= set(rule["source"].get("capabilities_all", []))
                and set(baseline.get("target", {}).get("capabilities_all", []))
                    <= set(rule["target"].get("capabilities_all", []))):
            return True
    return False


def _verified_comparison(data: dict) -> bool:
    if (data.get("kind") != "cinetwin.behavior_comparison"
            or data.get("acceptance_status")
            != "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE"
            or data.get("native_persistence_status")
            != "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS"
            or data.get("evaluation", {}).get("status") != "NO_FLAGGED_DIFFERENCES"
            or data.get("evaluation", {}).get("overall_cutscene_fidelity")
            != "NOT_ESTABLISHED"):
        return False
    a, b = data.get("generation_editor_pid"), data.get("observation_editor_pid")
    return (type(a) is int and type(b) is int and a > 0 and b > 0 and a != b)


def promote(store: str | Path, candidate_id: str, *,
            evidence_name: str, reviewer: str,
            held_out_passed: bool, regression_passed: bool) -> dict:
    """Record a reviewed native-verified approval; never change native assets.

    Independent evidence authenticity still requires actual workstation/QA
    review. This function checks hashes and required claim consistency; it
    cannot prove that files were genuinely captured from the editors.
    """
    root, _, approvals, evidence = _paths(store)
    item = _candidate(root, candidate_id)
    rule = item["rule"]
    if rule["ced"] not in _concepts():
        raise CEDRulebookError("Unknown semantic must first be added to the CED taxonomy.")
    if not _eligible_adapter(rule):
        raise CEDRulebookError("Mapping resolver/parameters need a registered, tested adapter.")
    if (not isinstance(reviewer, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{3,64}", reviewer)
            or held_out_passed is not True or regression_passed is not True):
        raise CEDRulebookError("Independent held-out validation, regressions and reviewer required.")
    if (not isinstance(evidence_name, str) or
            not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}\\.json", evidence_name)):
        raise CEDRulebookError("Evidence must use a safe file in the local evidence directory.")
    path = evidence / evidence_name
    data = _read(path, max_bytes=64 * 1024 * 1024)
    if not _verified_comparison(data):
        raise CEDRulebookError("Native saved/reopened comparison is not a verified pass.")
    record = {
        "kind": "cutsceneai.ced.rule_approval", "schema_version": VERSION,
        "candidate_id": candidate_id,
        "candidate_sha256": hashlib.sha256(
            (root / "candidates" / (candidate_id + ".json")).read_bytes()
        ).hexdigest(),
        "native_evidence_name": evidence_name,
        "native_evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "reviewer": reviewer, "held_out_passed": True,
        "regression_passed": True, "status": "APPROVED_FOR_GUARDED_RESOLUTION",
        "native_render_fidelity_certified": False,
    }
    approvals.mkdir(exist_ok=True)
    target = approvals / (candidate_id + ".json")
    if target.exists() or target.is_symlink():
        raise CEDRulebookError("Approved rules cannot be silently overwritten.")
    with target.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return record


def approved_rules(store: str | Path) -> list[dict]:
    """Load only immutable, verified approvals from a persistent local store."""
    root, candidates, approvals, evidence = _paths(store)
    if not root.exists():
        return []
    if not all(folder.is_dir() and not folder.is_symlink()
               for folder in (candidates, approvals, evidence)):
        raise CEDRulebookError("Local mapping rulebook store is incomplete or unsafe.")
    result = []
    seen = {row["rule_id"] for row in _baseline()}
    for path in sorted(approvals.glob("*.json")):
        approval = _read(path)
        candidate_id = path.stem
        candidate = _candidate(root, candidate_id)
        source = candidates / (candidate_id + ".json")
        native_path = evidence / str(approval.get("native_evidence_name", ""))
        if (approval.get("kind") != "cutsceneai.ced.rule_approval"
                or approval.get("schema_version") != VERSION
                or approval.get("candidate_id") != candidate_id
                or approval.get("status") != "APPROVED_FOR_GUARDED_RESOLUTION"
                or approval.get("held_out_passed") is not True
                or approval.get("regression_passed") is not True
                or approval.get("native_render_fidelity_certified") is not False
                or approval.get("candidate_sha256")
                != hashlib.sha256(source.read_bytes()).hexdigest()
                or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}\\.json",
                                    str(approval.get("native_evidence_name", "")))
                or approval.get("native_evidence_sha256")
                != hashlib.sha256(_read_file(native_path)).hexdigest()
                or not _verified_comparison(_read(native_path, max_bytes=64 * 1024 * 1024))
                or not _eligible_adapter(candidate["rule"])):
            raise CEDRulebookError("An approved CED rule has missing or altered evidence.")
        rule = candidate["rule"]
        if rule["ced"] not in _concepts() or rule["rule_id"] in seen:
            raise CEDRulebookError("Approved CED rule is unregistered or conflicts with baseline.")
        seen.add(rule["rule_id"])
        result.append(rule)
    return result


def _read_file(path: Path) -> bytes:
    _read(path, max_bytes=64 * 1024 * 1024)
    return path.read_bytes()
