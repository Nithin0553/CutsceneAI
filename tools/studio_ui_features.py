"""Read-only CED/UI evidence and safe candidate option validation.

Only source-project-owned Unity exports and active Studio candidate reports are
read. No engine mutations, asset imports or global source mapping writes.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STUDIO = str(ROOT / "packages" / "studio")
if STUDIO not in sys.path:
    sys.path.insert(0, STUDIO)

import feature_dispatch
import source_surface_gap


def capabilities() -> dict[str, Any]:
    catalog = feature_dispatch.catalog()
    potential = sum(
        bool(feature_dispatch.recipe(key, features=catalog).get("potential_builder_actions"))
        for key in catalog["_domain_for"]
    )
    families = []
    for family in catalog["feature_families"]:
        members = {
            semantic for semantic, domain in catalog["_domain_for"].items()
            if domain in family["ced_domains"]
        }
        candidate = sum(
            bool(feature_dispatch.recipe(s, features=catalog)
                 .get("potential_builder_actions"))
            for s in members
        )
        families.append({
            "id": family["id"], "semantic_count": len(members),
            "native_action_candidates": candidate,
            "state": "CATALOGUED_NOT_TRANSFER_VERIFIED",
        })
    return {
        "families": families,
        "catalog_version": catalog["version"],
        "catalog_sha256": catalog["_sha256"],
        "feature_families": len(catalog["feature_families"]),
        "semantic_domains": len(catalog["categories"]),
        "semantic_elements": len(catalog["_domain_for"]),
        "builder_actions": sorted(feature_dispatch.BUILDER_ACTIONS),
        "concepts_with_action_candidates": potential,
        "full_conversion_verified": False,
    }


def source_surfaces(config: dict[str, Any]) -> dict[str, Any]:
    project = str(config.get("unity_project") or "")
    if not project:
        return {"available": False, "options": [],
                "reason": "Connect a real Unity project folder."}
    exports = (Path(project).resolve() / "CutSceneAI" / "Exports").resolve()
    if not exports.is_dir():
        return {"available": True, "options": [],
                "reason": "In Unity, run Tools > CutsceneAI > Discover Installed Feature Surface."}
    candidates = sorted(
        (path for path in exports.glob("feature-surface-unity-*.json")
         if path.is_file() and path.resolve().is_relative_to(exports)),
        key=lambda path: path.stat().st_mtime_ns,
        reverse=True,
    )[:25]
    options: list[dict[str, Any]] = []
    for path in candidates:
        obj: dict[str, Any] = {"name": path.name, "path": str(path.resolve())}
        try:
            report = source_surface_gap.audit_files(config["csir"], path)
            ready = bool(report["project_identity_proven"]
                         and report["source_scope_matched"]
                         and report["unresolved_component_count"] == 0)
            unresolved_states = {
                "NATIVE_COMPONENT_EXTRACTION_OR_ADAPTER_REQUIRED",
                "MISSING_SOURCE_SCRIPT",
                "DUPLICATE_SOURCE_COMPONENT_IDENTITY",
            }
            findings = [
                {
                    "native_type": row["native_component"],
                    "object_path": row["hierarchy_path"],
                    "scene_path": row["scene_path"],
                    "state": row["state"],
                }
                for row in report["component_findings"]
                if row["state"] in unresolved_states
            ]
            if not report["source_scope_matched"]:
                findings.append({
                    "native_type": "SOURCE_SCOPE_NOT_VERIFIED",
                    "object_path": "(no matching source scene objects)",
                    "scene_path": "",
                    "state": "SOURCE_SCOPE_NOT_VERIFIED",
                })
            obj.update({
                "state": "MATCHED_COMPLETE" if ready else
                         "REVIEW_REQUIRED" if report["project_identity_proven"]
                         else "SOURCE_IDENTITY_NOT_PROVEN",
                "strict_ready": ready,
                "unresolved_components": report["unresolved_component_count"],
                "unresolved_findings": findings[:100],
                "findings_truncated": len(findings) > 100,
                "scoped_components": report["scoped_component_occurrences"],
                "project_identity_proven": report["project_identity_proven"],
                "source_scope_matched": report["source_scope_matched"],
            })
        except (ValueError, OSError, KeyError, TypeError) as exc:
            obj.update({"state": "INVALID", "strict_ready": False, "reason": str(exc)})
        options.append(obj)
    return {
        "available": True, "options": options,
        "reason": "" if options else (
            "No feature census found. In Unity: Tools > CutsceneAI > "
            "Discover Installed Feature Surface."
        ),
    }


def validate_options(config: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    allowed = {"source_feature_surface_path", "require_complete_source_features",
               "enable_actor_visibility_fallback"}
    if set(request) - allowed:
        raise ValueError("Unknown Studio conversion option.")
    for name in ("require_complete_source_features", "enable_actor_visibility_fallback"):
        if name in request and not isinstance(request[name], bool):
            raise ValueError(name + " must be Boolean.")
    choice = str(request.get("source_feature_surface_path") or "").strip()
    overrides: dict[str, Any] = {}
    if choice:
        options = source_surfaces(config)["options"]
        selected = next(
            (row for row in options
             if row["path"] == str(Path(choice).resolve()) and row["state"] != "INVALID"),
            None,
        )
        if selected is None:
            raise ValueError("Feature census must belong to the connected Unity project.")
        strict = request.get("require_complete_source_features", True)
        if strict and not selected["strict_ready"]:
            raise ValueError(
                "Strict source census blocked: "
                + str(selected.get("unresolved_components", 0))
                + " unresolved component/scope findings. "
                  "Expand source-component details on Review. For a labelled "
                  "best-effort Benchmark002 regression, uncheck strict source "
                  "completeness; full source coverage will remain unverified. "
                  "No engine assets were touched."
            )
        overrides["source_feature_surface_path"] = selected["path"]
        overrides["require_complete_source_features"] = strict
    elif request.get("require_complete_source_features"):
        raise ValueError("Strict completeness requires a matching Unity feature census.")
    if request.get("enable_actor_visibility_fallback"):
        overrides["enable_actor_visibility_fallback"] = True
    return overrides


def verification(workspace: Path, active_job: dict[str, Any],
                 loaded_job: dict[str, Any]) -> dict[str, Any]:
    """Read only the current job's candidate evidence; never open arbitrary paths."""
    job_id = str(active_job.get("job_id") or "")
    if len(job_id) != 32 or any(char not in "0123456789abcdef" for char in job_id):
        raise ValueError("Invalid active Studio job ID.")
    if loaded_job.get("job_id") != job_id:
        raise ValueError("Active job and persisted job mismatch.")
    candidate = Path(str(loaded_job.get("candidate_dir") or "")).resolve()
    if not candidate.is_relative_to((workspace / "candidates").resolve()):
        raise ValueError("Verification report is outside Studio candidate workspace.")
    out: dict[str, Any] = {
        "job_id": job_id, "available": True,
        "persistence": None, "hierarchy": None, "visual": None,
        "fidelity_verified": False,
    }
    for name, pattern, wanted in (
        ("persistence", "post-reopen-audit-" + job_id + ".json",
         "cutsceneai.studio.persistence_audit"),
        ("hierarchy", "hierarchy-audit-" + job_id + "-*.json",
         "cutsceneai.studio.hierarchy_persistence_audit"),
        ("visual", "visual-audit-" + job_id + "-*.json",
         "cutsceneai.studio.visual_readback_audit"),
    ):
        files = sorted(
            (p for p in candidate.glob(pattern) if p.is_file()
             and p.resolve().parent == candidate),
            key=lambda p: p.stat().st_mtime_ns, reverse=True,
        )
        if not files:
            continue
        from json import loads
        data = loads(files[0].read_text(encoding="utf-8-sig"))
        if data.get("kind") != wanted:
            continue
        report = {
            "status": data.get("status"), "path": str(files[0]),
            "fidelity_verified": False, "restart_verified": False,
        }
        if name == "persistence":
            report.update({
                "native_structure": data.get("native_structure_status"),
                "assets": data.get("assets_class_and_disk_verified"),
                "assets_expected": data.get("asset_count"),
                "actors": data.get("actors_unique_and_class_verified"),
                "actors_expected": data.get("actor_count"),
            })
        elif name == "hierarchy":
            report.update({
                "parent_links": data.get("direct_parent_links_verified"),
                "fully_checked": data.get("direct_edges_verified"),
                "parent_links_expected": data.get("direct_edges_expected"),
                "unresolved_source_parents": len(data.get("unresolved_source_parents", [])),
                "source_groups": data.get("source_group_ancestors", []),
            })
        else:
            report.update({
                "material_slots": data.get("material_slots"),
                "default_material_slots": data.get("material_slots_engine_default"),
                "empty_material_slots": data.get("material_slots_empty"),
                "nondefault_material_slots": data.get("material_slots_nondefault"),
                "environment": data.get("environment_actor_counts") or {},
                "visual_issues": data.get("visual_issues") or [],
                "render_fidelity_verified": False,
            })
        out[name] = report
    return out
