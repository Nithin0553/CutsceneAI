"""Opt-in, local Unity Editor source-export request/receipt contract.

The Studio service never opens or edits Unity scenes. Its one permitted native
operation asks a running, user-enabled Unity Editor companion to export the
currently selected Timeline and a matching project feature census.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

BRIDGE_KIND = "cutsceneai.unity.source_bridge"
ACTION = "EXPORT_SELECTED_TIMELINE_AND_CENSUS"
ID_RE = re.compile(r"[0-9a-f]{32}\Z")
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")


class UnityBridgeError(ValueError):
    """Source analysis request is invalid, unsafe or cannot be verified."""


def _root(value: str | Path) -> Path:
    original = Path(value).expanduser()
    if original.is_symlink():
        raise UnityBridgeError("Unity project root may not be a symlink.")
    root = original.resolve()
    if not root.is_dir():
        raise UnityBridgeError("Select an existing Unity project root.")
    for child in ("Assets", "ProjectSettings"):
        folder = root / child
        if folder.is_symlink() or not folder.is_dir() or not folder.resolve().is_relative_to(root):
            raise UnityBridgeError("Selected folder is not a supported Unity project root.")
    return root


def _bridge(root: Path) -> Path:
    # Refuse symlink-based redirection of requests or receipts outside project.
    parents = [root / "CutSceneAI", root / "CutSceneAI" / "StudioBridge"]
    parents += [parents[-1] / name for name in ("requests", "receipts", "evidence")]
    if any(p.is_symlink() or (p.exists() and not p.is_dir()) for p in parents):
        raise UnityBridgeError("Unsafe Unity source bridge directory.")
    return root / "CutSceneAI" / "StudioBridge"


def _load(path: Path, limit: int = 16 * 1024) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise UnityBridgeError("Missing, oversized, or redirected Unity bridge record.")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise UnityBridgeError("Invalid Unity bridge JSON record.") from exc
    if not isinstance(value, dict):
        raise UnityBridgeError("Unity bridge JSON must be an object.")
    return value


def _safe_ticket(request_id: str) -> str:
    if not isinstance(request_id, str) or ID_RE.fullmatch(request_id) is None:
        raise UnityBridgeError("Invalid Unity source request identity.")
    return request_id


def request_snapshot(project_root: str | Path) -> dict:
    """Create one immutable export request, never start Unity or execute code."""
    root = _root(project_root)
    bridge = _bridge(root)
    requests = bridge / "requests"
    requests.mkdir(parents=True, exist_ok=True)
    ticket = uuid.uuid4().hex
    record = {
        "kind": BRIDGE_KIND,
        "schema_version": "1",
        "request_id": ticket,
        "action": ACTION,
    }
    with (requests / (ticket + ".json")).open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True)
        stream.write("\n")
    return {
        "request_id": ticket,
        "status": "WAITING_FOR_UNITY",
        "action": ACTION,
        "instruction": (
            "Open the selected Unity project in Unity Editor, select a saved "
            "GameObject containing a PlayableDirector/TimelineAsset, and enable "
            "Tools > CutsceneAI > Studio Bridge > Enable Source Bridge."
        ),
    }


def _evidence(root: Path, relative_path: object, expected_sha: object, suffix: str) -> str:
    if not isinstance(relative_path, str) or not relative_path or "\\" in relative_path:
        raise UnityBridgeError("Invalid source evidence location.")
    raw = Path(relative_path)
    if raw.is_absolute() or any(p in {"..", "."} for p in raw.parts):
        raise UnityBridgeError("Source evidence must use a project-relative path.")
    path = root.joinpath(*raw.parts)
    if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
        raise UnityBridgeError("Unity evidence is missing or redirects outside the project.")
    if not path.name.endswith(suffix):
        raise UnityBridgeError("Incorrect Unity evidence file format.")
    if not isinstance(expected_sha, str) or SHA_RE.fullmatch(expected_sha) is None:
        raise UnityBridgeError("Missing source evidence digest.")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
        raise UnityBridgeError("Unity evidence has changed since export.")
    return str(path.resolve())


def snapshot_status(project_root: str | Path, request_id: str) -> dict:
    """Validate a native Unity receipt and both immutable evidence hashes."""
    root = _root(project_root)
    bridge = _bridge(root)
    ticket = _safe_ticket(request_id)
    request = _load(bridge / "requests" / (ticket + ".json"), limit=4096)
    if (request.get("kind") != BRIDGE_KIND or request.get("schema_version") != "1"
            or request.get("request_id") != ticket or request.get("action") != ACTION):
        raise UnityBridgeError("Unity request provenance does not match.")
    receipt_path = bridge / "receipts" / (ticket + ".json")
    if not receipt_path.exists():
        return {"request_id": ticket, "status": "WAITING_FOR_UNITY"}
    receipt = _load(receipt_path)
    if (receipt.get("kind") != BRIDGE_KIND or receipt.get("schema_version") != "1"
            or receipt.get("request_id") != ticket):
        raise UnityBridgeError("Stale or mismatched Unity Editor receipt.")
    state = receipt.get("status")
    if state == "BLOCKED":
        return {"request_id": ticket, "status": "BLOCKED",
                "reason": str(receipt.get("reason") or "Unity source extraction failed.")[:500]}
    if state != "SUCCEEDED":
        raise UnityBridgeError("Unknown Unity Editor receipt status.")
    csir = _evidence(root, receipt.get("csir_path"), receipt.get("csir_sha256"), ".csir.json")
    census = _evidence(root, receipt.get("census_path"), receipt.get("census_sha256"), ".json")
    source_document = _load(Path(csir), limit=128 * 1024 * 1024)
    census_document = _load(Path(census), limit=128 * 1024 * 1024)
    if (source_document.get("schema_version") != "0.1.0"
            or source_document.get("source", {}).get("engine") != "unity"):
        raise UnityBridgeError("Exported CSIR is not a supported Unity source document.")
    if (census_document.get("kind") != "cutsceneai.engine.feature_surface"
            or census_document.get("engine") != "unity"):
        raise UnityBridgeError("Exported source census is not a Unity feature surface.")
    fingerprint = source_document.get("source", {}).get("project_fingerprint")
    if (not isinstance(fingerprint, str) or not fingerprint
            or fingerprint != census_document.get("project_fingerprint")):
        raise UnityBridgeError("CSIR and census source project identity do not match.")
    return {
        "request_id": ticket, "status": "SUCCEEDED",
        "csir_path": csir, "census_path": census,
        "csir_sha256": receipt["csir_sha256"],
        "census_sha256": receipt["census_sha256"],
        "fidelity_verified": False,
        "next_action": "Refresh exports, choose the new CSIR and census, then prepare the transfer.",
    }
