"""Independent, read-only source-to-target hierarchy audit for Studio.

Compare authoritative CSIR parent_entity_id and approved target mapping with
actual actor attachments after reopening the Unreal staging project. Never
create, attach, move, save, or delete editor objects. This structural snapshot
does not establish time-evaluated world-motion or playback equivalence.
"""
from __future__ import annotations

import hashlib
import json
import ntpath
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CINETWIN = ROOT / "packages" / "cinetwin"
if str(CINETWIN) not in sys.path:
    sys.path.insert(0, str(CINETWIN))

from hierarchy_plan import HierarchyPlanError, plan_actor_hierarchy


class HierarchyAuditError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise HierarchyAuditError("Expected JSON object: " + str(path))
    return value


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _project_key(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(value).replace("/", "\\")))


def _project(api: Any) -> str:
    raw = str(api.Paths.get_project_file_path())
    converter = getattr(api.Paths, "convert_relative_path_to_full", None)
    return str(converter(raw)) if callable(converter) else raw


def _level(api: Any) -> str:
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    return str(world.get_path_name()).split(".")[0]


def _root_component(actor: Any) -> Any | None:
    """UE 5.8 exposes Actor.root_component as an editor property, not necessarily a method."""
    getter = getattr(actor, "get_editor_property", None)
    if callable(getter):
        try:
            result = getter("root_component")
            if result is not None:
                return result
        except (AttributeError, RuntimeError, TypeError):
            pass
    try:
        result = getattr(actor, "root_component", None)
        if result is not None:
            return result
    except (AttributeError, RuntimeError, TypeError):
        pass
    method = getattr(actor, "get_root_component", None)
    if callable(method):
        try:
            return method()
        except (AttributeError, RuntimeError, TypeError):
            return None
    return None


def _mobility(actor: Any) -> str | None:
    component = _root_component(actor)
    if component is None:
        return None
    getter = getattr(component, "get_editor_property", None)
    value = None
    if callable(getter):
        try:
            value = getter("mobility")
        except (AttributeError, RuntimeError, TypeError):
            pass
    if value is None:
        try:
            value = getattr(component, "mobility", None)
        except (AttributeError, RuntimeError, TypeError):
            return None
    if value is None:
        return None
    name = str(getattr(value, "name", value)).upper()
    if "MOVABLE" in name:
        return "MOVABLE"
    if "STATIONARY" in name:
        return "STATIONARY"
    if "STATIC" in name:
        return "STATIC"
    return None


def _socket(actor: Any) -> str | None:
    """Distinguish an unexposed API from a proven empty attachment socket."""
    getter = getattr(actor, "get_attach_parent_socket_name", None)
    if not callable(getter):
        component = _root_component(actor)
        getter = getattr(component, "get_attach_socket_name", None)
    if not callable(getter):
        return None
    try:
        value = str(getter())
    except Exception:
        return None
    return "" if value.strip().lower() in {"", "none", "name('none')"} else value


def _actors(api: Any) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for actor in api.get_editor_subsystem(api.EditorActorSubsystem).get_all_level_actors():
        result.setdefault(str(actor.get_actor_label()), []).append(actor)
    return result


def audit(job_path: str | Path, output_path: str | Path, *, unreal_api: Any = None) -> dict[str, Any]:
    """Run a fresh editor-only attachment observation; save one immutable JSON."""
    api = unreal_api
    if api is None:
        import unreal as api

    job_file = Path(job_path).resolve()
    output = Path(output_path).resolve()
    if output.exists() or not output.parent.is_dir():
        raise HierarchyAuditError("Audit already exists or its output folder is unavailable.")
    job = _load(job_file)
    if job.get("kind") != "cutsceneai.studio.local_unreal_job":
        raise HierarchyAuditError("Invalid Studio job.")
    candidate = Path(job["candidate_dir"]).resolve()
    if (job_file.parent.name != "jobs"
            or candidate.parent.name != "candidates"
            or candidate.parent.parent != job_file.parent.parent
            or output.parent != candidate):
        raise HierarchyAuditError("Job, candidate and output must belong to one Studio workspace.")
    if (_project_key(_project(api)) != _project_key(job["expected_project"])
            or _level(api) != job["expected_level"]):
        raise HierarchyAuditError("Incorrect loaded Unreal project or level. No editor changes made.")

    csir_file = Path(job["csir"]).resolve()
    mapping_file = Path(job["mapping"]).resolve()
    manifest_file = candidate / "automatic-setup.json"
    plan_file = candidate / "transfer-plan.json"
    manifest = _load(manifest_file)
    plan = _load(plan_file)
    if manifest.get("kind") != "cutsceneai.studio.automatic_setup_plan":
        raise HierarchyAuditError("Missing approved automatic setup manifest.")
    for field, path, expected in (
        ("source_csir_sha256", csir_file, manifest.get("source_csir_sha256")),
        ("mapping_sha256", mapping_file, manifest.get("mapping_sha256")),
        ("transfer_plan_sha256", plan_file, manifest.get("transfer_plan_sha256")),
    ):
        if not isinstance(expected, str) or _sha(path) != expected:
            raise HierarchyAuditError("Stale or unverified source evidence: " + field)
    csir, mapping = _load(csir_file), _load(mapping_file)
    if csir.get("source", {}).get("engine") != "unity":
        raise HierarchyAuditError("Expected source Unity CSIR.")
    if plan.get("sequence_asset_path") != job.get("sequence_path"):
        raise HierarchyAuditError("Transfer plan targets a different Level Sequence.")
    target_bindings = plan.get("bindings") or {}
    for row in manifest.get("actors", []):
        name, label = str(row["name"]), str(row["label"])
        if (target_bindings.get(name) != label
                or (mapping.get("entities", {}).get(name) or {}).get("actor_label") != label):
            raise HierarchyAuditError("Actor identity differs between source mapping and setup: " + name)

    try:
        source = plan_actor_hierarchy(csir, mapping)
    except HierarchyPlanError as exc:
        raise HierarchyAuditError("Unsafe source hierarchy: " + str(exc)) from exc

    expected_labels = {str(row["label"]) for row in manifest["actors"]}
    mapped_labels = ({row["actor_label"] for row in source["planned_actor_attachments"]}
                     | {row["actor_label"] for row in source["mapped_source_roots"]}
                     | {row["actor_label"] for row in source["unresolved_source_parents"]})
    if mapped_labels != expected_labels:
        raise HierarchyAuditError("Source hierarchy actor inventory differs from approved import.")

    by_label = _actors(api)
    problems = []
    incomplete = []
    rows = []
    for edge in source["planned_actor_attachments"]:
        child, parent_label = edge["actor_label"], edge["parent_actor_label"]
        matches = by_label.get(child, [])
        parents = by_label.get(parent_label, [])
        row = {"source_name": edge["entity_name"], "actor_label": child,
               "source_parent_name": edge["source_parent_name"],
               "expected_parent_label": parent_label, "observed_parent_label": None,
               "socket": None, "mobility": None, "parent_mobility": None,
               "parent_link_status": "INCOMPLETE", "status": "INCOMPLETE"}
        if len(matches) != 1 or len(parents) != 1:
            row["status"] = "FAIL"
            problems.append("MISSING_OR_DUPLICATE_MAPPED_ACTOR: " + child + " -> " + parent_label)
        else:
            actor = matches[0]
            getter = getattr(actor, "get_attach_parent_actor", None)
            actual = getter() if callable(getter) else None
            row["observed_parent_label"] = str(actual.get_actor_label()) if actual else None
            row["socket"] = _socket(actor)
            row["mobility"] = _mobility(actor)
            row["parent_mobility"] = _mobility(parents[0])
            if not callable(getter):
                incomplete.append("ATTACHMENT_API_UNAVAILABLE: " + child)
            elif (row["observed_parent_label"] != parent_label
                  or (callable(getattr(actual, "get_path_name", None))
                      and callable(getattr(parents[0], "get_path_name", None))
                      and str(actual.get_path_name()) != str(parents[0].get_path_name()))):
                row["status"] = "FAIL"
                row["parent_link_status"] = "FAIL"
                problems.append("PARENT_MISMATCH: " + child + " -> " + str(row["observed_parent_label"]))
            else:
                row["parent_link_status"] = "PASS"
                if row["socket"] is None:
                    incomplete.append("SOCKET_READBACK_UNAVAILABLE: " + child)
                elif row["socket"]:
                    row["status"] = "FAIL"
                    problems.append("UNEXPECTED_SOCKET_ATTACHMENT: " + child + " @ " + row["socket"])
                elif row["mobility"] is None or row["parent_mobility"] is None:
                    incomplete.append("MOBILITY_READBACK_UNAVAILABLE: " + child)
                elif row["mobility"] != "MOVABLE" or row["parent_mobility"] != "MOVABLE":
                    row["status"] = "FAIL"
                    problems.append("NON_MOVABLE_ATTACHED_ACTOR: " + child)
                else:
                    row["status"] = "PASS"
        rows.append(row)

    roots = []
    for root in source["mapped_source_roots"]:
        label = root["actor_label"]
        matches = by_label.get(label, [])
        if len(matches) != 1:
            roots.append({"actor_label": label, "status": "FAIL"})
            problems.append("MISSING_OR_DUPLICATE_ROOT: " + label)
            continue
        getter = getattr(matches[0], "get_attach_parent_actor", None)
        if not callable(getter):
            roots.append({"actor_label": label, "status": "INCOMPLETE"})
            incomplete.append("ROOT_PARENT_API_UNAVAILABLE: " + label)
        else:
            attached = getter()
            roots.append({"actor_label": label,
                          "observed_parent_label": str(attached.get_actor_label()) if attached else None,
                          "status": "PASS" if attached is None else "FAIL"})
            if attached is not None:
                problems.append("UNEXPECTED_ROOT_PARENT: " + label)

    for unresolved in source["unresolved_source_parents"]:
        incomplete.append("SOURCE_PARENT_NOT_MAPPED_AS_ACTOR: " + unresolved["entity_name"])

    status = ("FAIL" if problems else "INCOMPLETE" if incomplete else "PASS")
    report = {
        "kind": "cutsceneai.studio.hierarchy_persistence_audit",
        "schema_version": "0.1.0",
        "status": status,
        "source_csir_sha256": _sha(csir_file),
        "mapping_sha256": _sha(mapping_file),
        "transfer_plan_sha256": _sha(plan_file),
        "unreal_project": _project(api), "unreal_level": _level(api),
        "direct_attachments": rows, "source_roots": roots,
        "unresolved_source_parents": source["unresolved_source_parents"],
        "direct_edges_expected": len(rows),
        "direct_parent_links_verified": sum(row["parent_link_status"] == "PASS" for row in rows),
        "direct_edges_verified": sum(row["status"] == "PASS" for row in rows),
        "root_actors_verified": sum(row["status"] == "PASS" for row in roots),
        "errors": problems, "incomplete": incomplete,
        "editor_modified": False, "fidelity_verified": False, "restart_verified": False,
        "limitations": [
            "Only mapped direct actor parent relationships can be verified; unmapped intermediate transforms remain incomplete.",
            "Sampled evaluated world trajectories, skeletal joints, socket motion, physics and playback are not evaluated.",
            "Observing the reopened editor does not cryptographically prove an editor process restart.",
            "Mobility is observed; source-aligned animation-dependent mobility requirements need a separate behavior gate.",
        ],
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return report


def audit_latest(workspace: str | Path | None = None, *, unreal_api: Any = None) -> dict[str, Any]:
    root = Path(workspace).resolve() if workspace is not None else (
        Path.home() / ".cutsceneai-studio" / "runs"
    )
    pointer = _load(root / "active-job.json")
    job_id = str(pointer["job_id"])
    if len(job_id) != 32 or any(char not in "0123456789abcdef" for char in job_id):
        raise HierarchyAuditError("Invalid job ID.")
    job_file = root / "jobs" / (job_id + ".json")
    job = _load(job_file)
    candidate = Path(job["candidate_dir"]).resolve()
    if not candidate.is_relative_to((root / "candidates").resolve()):
        raise HierarchyAuditError("Candidate path outside Studio workspace.")
    path = candidate / ("hierarchy-audit-" + job_id + "-" + uuid.uuid4().hex[:8] + ".json")
    result = audit(job_file, path, unreal_api=unreal_api)
    print("[CutSceneAI Studio] HIERARCHY: {} | parent links {}/{} | fully checked links {}/{} | roots {}/{} | unresolved source parents {}".format(
        result["status"], result["direct_parent_links_verified"], result["direct_edges_expected"],
        result["direct_edges_verified"], result["direct_edges_expected"],
        result["root_actors_verified"], len(result["source_roots"]),
        len(result["unresolved_source_parents"])))
    for item in result["errors"] + result["incomplete"]:
        print("[CutSceneAI Studio] Hierarchy detail: " + item)
    print("[CutSceneAI Studio] Hierarchy report: " + str(path))
    return result
