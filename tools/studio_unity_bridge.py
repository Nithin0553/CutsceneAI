"""Opt-in, local Unity Editor source-export request/receipt contract.

The Studio service never opens or edits Unity scenes. Its one permitted native
operation asks a running, user-enabled Unity Editor companion to export the
currently selected Timeline and a matching project feature census.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BRIDGE_KIND = "cutsceneai.unity.source_bridge"
ACTION = "EXPORT_SELECTED_TIMELINE_AND_CENSUS"
CAPTURE_ACTION = "CAPTURE_SELECTED_TIMELINE_BEHAVIOR"
MAX_CINETWIN_SAMPLES = 3000
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


def editor_status(project_root: str | Path) -> dict:
    """Read-only project-scoped Unity presence, with actionable diagnostics.

    A heartbeat is diagnostic only; it cannot authorize native extraction,
    replace request receipts or attest cutscene fidelity.
    """
    offline = {
        "connected": False,
        "status": "WAITING_FOR_UNITY_EDITOR",
        "next_action": (
            "Open the exact selected Unity project and enable Tools > "
            "CutsceneAI > Studio Bridge > Enable Source Bridge. "
            "The bridge must write CutSceneAI/StudioBridge/unity-editor.json."
        ),
    }
    try:
        root = _root(project_root)
        marker = _bridge(root) / "unity-editor.json"
        if not marker.is_file():
            return offline
        record = _load(marker, 4096)
        version = record.get("bridge_version")
        if version != "unity-editor-v0.2":
            return {
                "connected": False, "status": "UNSUPPORTED_UNITY_BRIDGE_VERSION",
                "bridge_version": str(version or "UNKNOWN")[:80],
                "next_action": (
                    "Unity is running an incompatible source bridge. Verify "
                    "Package Manager points to the current repository package "
                    "and let Unity recompile before re-enabling it."
                ),
            }
        if record.get("source_bridge_enabled") is not True:
            return {
                "connected": False, "status": "UNITY_SOURCE_BRIDGE_DISABLED",
                "next_action": (
                    "Enable Source Bridge in this exact Unity project. "
                    "Bridge consent is intentionally project-scoped."
                ),
            }
        if (record.get("kind") != "cutsceneai.unity.editor_presence"
                or record.get("schema_version") != "1"
                or type(record.get("editor_pid")) is not int
                or record["editor_pid"] <= 0
                or record.get("editor_mode") not in ("PLAY_MODE", "EDIT_MODE")):
            return {
                "connected": False, "status": "INVALID_OR_DISABLED_UNITY_BRIDGE",
                "next_action": (
                    "Unity's heartbeat fields are invalid. Confirm the Unity "
                    "Editor compiled the current bridge package."
                ),
            }
        reported = record.get("project_root")
        if (not isinstance(reported, str) or not Path(reported).is_absolute()
                or Path(reported).resolve() != root):
            return {
                "connected": False, "status": "WRONG_UNITY_PROJECT",
                "next_action": (
                    "Studio is reading a heartbeat for another Unity project. "
                    "Check the folder chosen in Studio matches the open Editor."
                ),
            }
        tick = datetime.fromisoformat(str(record["heartbeat"]).replace("Z", "+00:00"))
        if tick.tzinfo is None:
            return {
                "connected": False, "status": "INVALID_UNITY_HEARTBEAT",
                "next_action": "Unity's bridge heartbeat timestamp is invalid.",
            }
        age = (datetime.now(timezone.utc) - tick).total_seconds()
        if not 0 <= age < 8:
            return {
                "connected": False, "status": "UNITY_COMPANION_RELOADING_OR_OFFLINE",
                "next_action": (
                    "The Unity heartbeat is stale. Check the Unity Console "
                    "for bridge file-write errors or a script-compilation failure."
                ),
            }
        return {
            "connected": True, "status": "CONNECTED",
            "project_root": str(root), "editor_pid": record["editor_pid"],
            "editor_mode": record["editor_mode"],
            "bridge_version": record["bridge_version"],
            "age_seconds": round(age, 1),
            "restart_required": False,
        }
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, UnityBridgeError):
        return {
            "connected": False, "status": "INVALID_UNITY_BRIDGE_HEARTBEAT",
            "next_action": (
                "The Unity heartbeat is malformed or cannot be read. "
                "Check project permissions and the StudioBridge directory."
            ),
        }

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


def _evidence(
    root: Path, relative_path: object, expected_sha: object, suffix: str,
    *, limit: int = 128 * 1024 * 1024,
) -> str:
    """Verify bounded evidence in streaming chunks before parsing large JSON."""
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
    size = path.stat().st_size
    if not 0 < size <= limit:
        raise UnityBridgeError(
            "Unity evidence exceeds the bounded " +
            str(limit // (1024 * 1024)) + " MiB source file limit or is empty."
        )
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_sha:
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



def _sampling():
    """Load the single canonical CineTwin sampling/validation implementation."""
    location = str(Path(__file__).resolve().parents[1] / "packages" / "cinetwin")
    if location not in sys.path:
        sys.path.insert(0, location)
    from sampling_plan import SamplingPlanError, plan_file, validate_capture
    return SamplingPlanError, plan_file, validate_capture


def request_behavior_capture(project_root: str | Path, source_request_id: str) -> dict:
    """Queue measured Unity Play Mode source capture from an exact verified CSIR.

    Studio never enters Play Mode, evaluates timelines, runs Unity scripts,
    changes scenes or substitutes simulated observations. The opt-in Unity
    companion processes the request only while the source is already playing.
    """
    root = _root(project_root)
    original = snapshot_status(root, _safe_ticket(source_request_id))
    if original["status"] != "SUCCEEDED":
        raise UnityBridgeError("An exact completed Unity snapshot is required for CineTwin.")
    bridge = _bridge(root)
    evidence = bridge / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    ticket = uuid.uuid4().hex
    plan = evidence / (ticket + ".cinetwin.sampling-plan.json")
    # Exclusive reservation ensures no pre-existing or symlinked file can
    # quietly be reused as source sampling instructions.
    with plan.open("x", encoding="utf-8"):
        pass
    error_type, plan_file, _ = _sampling()
    try:
        prepared = plan_file(original["csir_path"], plan)
        if (len(prepared["samples"]) > MAX_CINETWIN_SAMPLES
                or len(prepared["samples"]) < 2):
            raise UnityBridgeError(
                "Source Timeline has too many CineTwin samples for automatic "
                "Play Mode observation; a bounded capture must be prepared separately."
            )
        plan_sha = hashlib.sha256(plan.read_bytes()).hexdigest()
        record = {
            "kind": BRIDGE_KIND, "schema_version": "1",
            "request_id": ticket, "action": CAPTURE_ACTION,
            "source_request_id": source_request_id,
            "source_csir_sha256": original["csir_sha256"],
            "plan_path": "CutSceneAI/StudioBridge/evidence/" + plan.name,
            "plan_sha256": plan_sha,
        }
        requests = bridge / "requests"
        requests.mkdir(parents=True, exist_ok=True)
        with (requests / (ticket + ".json")).open("x", encoding="utf-8") as stream:
            json.dump(record, stream, sort_keys=True)
            stream.write("\n")
    except (OSError, ValueError, KeyError, TypeError, error_type) as exc:
        plan.unlink(missing_ok=True)
        raise UnityBridgeError("Cannot prepare source CineTwin capture: " + str(exc)) from exc
    return {
        "request_id": ticket,
        "status": "WAITING_FOR_UNITY_PLAY_MODE",
        "instruction": (
            "CineTwin requires source Play Mode. Enter Play Mode in the selected "
            "Unity Editor. The enabled Studio Bridge will capture the verified "
            "Timeline automatically without a file picker; Studio will resume."
        ),
        "sample_count": len(prepared["samples"]),
        "fidelity_verified": False,
    }


def behavior_capture_status(project_root: str | Path, capture_request_id: str) -> dict:
    """Validate the source-attested CineTwin capture, never invent measured poses."""
    root = _root(project_root)
    bridge = _bridge(root)
    ticket = _safe_ticket(capture_request_id)
    request = _load(bridge / "requests" / (ticket + ".json"), limit=4096)
    if (request.get("kind") != BRIDGE_KIND or request.get("schema_version") != "1"
            or request.get("request_id") != ticket or request.get("action") != CAPTURE_ACTION):
        raise UnityBridgeError("CineTwin capture request identity mismatch.")
    original = snapshot_status(root, _safe_ticket(request.get("source_request_id")))
    if (original["status"] != "SUCCEEDED"
            or request.get("source_csir_sha256") != original["csir_sha256"]):
        raise UnityBridgeError("CineTwin capture no longer matches its Unity source.")
    expected_plan = "CutSceneAI/StudioBridge/evidence/" + ticket + ".cinetwin.sampling-plan.json"
    if request.get("plan_path") != expected_plan:
        raise UnityBridgeError("Unexpected source CineTwin plan path.")
    plan_path = _evidence(
        root, expected_plan, request.get("plan_sha256"),
        ".cinetwin.sampling-plan.json", limit=8 * 1024 * 1024,
    )
    receipt_path = bridge / "receipts" / (ticket + ".json")
    if not receipt_path.exists():
        return {
            "request_id": ticket, "status": "WAITING_FOR_UNITY_PLAY_MODE",
            "message": "Enter Play Mode in Unity to collect source CineTwin samples.",
        }
    receipt = _load(receipt_path)
    if (receipt.get("kind") != BRIDGE_KIND or receipt.get("schema_version") != "1"
            or receipt.get("request_id") != ticket
            or receipt.get("plan_sha256") != request.get("plan_sha256")):
        raise UnityBridgeError("CineTwin receipt or sampling plan identity mismatch.")
    if receipt.get("status") == "BLOCKED":
        return {
            "request_id": ticket, "status": "BLOCKED",
            "reason": str(receipt.get("reason") or "Native Unity CineTwin capture blocked.")[:500],
        }
    if receipt.get("status") != "SUCCEEDED":
        raise UnityBridgeError("Unexpected Unity CineTwin receipt status.")
    target_path = "CutSceneAI/StudioBridge/evidence/" + ticket + ".cinetwin.behavior.json"
    if receipt.get("capture_path") != target_path:
        raise UnityBridgeError("Unexpected source CineTwin capture path.")
    capture_path = _evidence(root, target_path, receipt.get("capture_sha256"), ".cinetwin.behavior.json")
    plan = _load(Path(plan_path), limit=8 * 1024 * 1024)
    capture = _load(Path(capture_path), limit=128 * 1024 * 1024)
    _, _, validate_capture = _sampling()
    try:
        validation = validate_capture(plan, capture)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise UnityBridgeError("Invalid native CineTwin sample evidence.") from exc
    if validation["failures"]:
        raise UnityBridgeError(
            "Native Unity CineTwin capture failed validation: " +
            "; ".join(validation["failures"][:3])
        )
    return {
        "request_id": ticket, "status": "SUCCEEDED",
        "capture_path": capture_path, "capture_sha256": receipt["capture_sha256"],
        "plan_sha256": receipt["plan_sha256"],
        "source_capture_validated": True,
        "fidelity_verified": False,
    }
