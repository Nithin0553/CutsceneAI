"""Source-grounded Studio hierarchy audit tests (not a substitute for real editor replay)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_studio_persistence_audit import _write, fixture

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "studio_hierarchy_audit", ROOT / "integrations/unreal/studio_hierarchy_audit.py"
)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class Actor:
    def __init__(self, label, parent=None, *, mobility="MOVABLE", socket="None", path=None):
        self.label, self.parent = label, parent
        self.mobility, self.socket = mobility, socket
        self.path = path or "/Game/Testing/L_Test:PersistentLevel." + label

    def get_actor_label(self):
        return self.label

    def get_path_name(self):
        return self.path

    def get_attach_parent_actor(self):
        return self.parent

    def get_attach_parent_socket_name(self):
        return self.socket

    def get_root_component(self):
        if self.mobility is None:
            return None
        return NS(get_editor_property=lambda key: NS(name=self.mobility))


def prepared(tmp_path):
    _root, jobfile, candidate, fake, _assets, actors = fixture(tmp_path)
    csir_path = tmp_path / "source.csir.json"
    mapping_path = tmp_path / "source.mapping.json"
    source = {
        "source": {"engine": "unity"}, "cutscene_id": "synthetic",
        "entities": [
            {"entity_id": "hero", "name": "Hero", "ced_type": "entity.character",
             "parent_entity_id": None},
            {"entity_id": "cam", "name": "CAM", "ced_type": "entity.camera",
             "parent_entity_id": "hero"},
        ],
    }
    mapping = {
        "entities": {
            "Hero": {"actor_label": "CSAI_Hero"},
            "CAM": {"actor_label": "CSAI_CAM"},
        },
    }
    _write(csir_path, source)
    _write(mapping_path, mapping)
    job = json.loads(jobfile.read_text(encoding="utf-8"))
    job["csir"], job["mapping"] = str(csir_path), str(mapping_path)
    _write(jobfile, job)
    _write(candidate / "transfer-plan.json", {
        "sequence_asset_path": job["sequence_path"],
        "bindings": {"Hero": "CSAI_Hero", "CAM": "CSAI_CAM"},
    })
    manifest_path = candidate / "automatic-setup.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_csir_sha256"] = AUDIT._sha(csir_path)
    manifest["mapping_sha256"] = AUDIT._sha(mapping_path)
    manifest["transfer_plan_sha256"] = AUDIT._sha(candidate / "transfer-plan.json")
    _write(manifest_path, manifest)
    parent = Actor("CSAI_Hero")
    child = Actor("CSAI_CAM", parent=parent)
    actors[:] = [parent, child]
    return jobfile, candidate, fake, actors, csir_path, mapping_path


def test_verified_parent_mobility_socket_and_root_are_read_without_mutation(tmp_path):
    jobfile, candidate, fake, _actors, _csir, _mapping = prepared(tmp_path)
    output = candidate / "hierarchy.json"
    result = AUDIT.audit(jobfile, output, unreal_api=fake)
    assert result["status"] == "PASS"
    assert result["direct_edges_expected"] == result["direct_edges_verified"] == 1
    assert result["root_actors_verified"] == 1
    assert result["direct_attachments"][0]["mobility"] == "MOVABLE"
    assert result["direct_attachments"][0]["socket"] == ""
    assert result["editor_modified"] is False
    assert result["fidelity_verified"] is False
    assert result["restart_verified"] is False
    assert output.is_file()
    with pytest.raises(AUDIT.HierarchyAuditError, match="already exists"):
        AUDIT.audit(jobfile, output, unreal_api=fake)


def test_different_python_wrapper_same_unreal_actor_path_is_valid(tmp_path):
    jobfile, candidate, fake, actors, _csir, _mapping = prepared(tmp_path)
    cloned_parent = Actor("CSAI_Hero", path=actors[0].get_path_name())
    actors[1].parent = cloned_parent
    assert AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)["status"] == "PASS"


def test_wrong_parent_is_a_real_hierarchy_failure(tmp_path):
    jobfile, candidate, fake, actors, _csir, _mapping = prepared(tmp_path)
    actors[1].parent = None
    result = AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)
    assert result["status"] == "FAIL"
    assert result["direct_edges_verified"] == 0
    assert any("PARENT_MISMATCH" in item for item in result["errors"])


def test_unexposed_mobility_or_socket_is_incomplete_not_pass(tmp_path):
    jobfile, candidate, fake, actors, _csir, _mapping = prepared(tmp_path)
    actors[1].mobility = None
    result = AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)
    assert result["status"] == "INCOMPLETE"
    assert result["direct_edges_verified"] == 0
    assert any("MOBILITY_READBACK_UNAVAILABLE" in item for item in result["incomplete"])


def test_nonempty_unexpected_socket_is_failure(tmp_path):
    jobfile, candidate, fake, actors, _csir, _mapping = prepared(tmp_path)
    actors[1].socket = "Hand_R"
    result = AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)
    assert result["status"] == "FAIL"
    assert any("UNEXPECTED_SOCKET_ATTACHMENT" in item for item in result["errors"])


def test_unmapped_intermediate_source_parent_is_explicitly_incomplete(tmp_path):
    jobfile, candidate, fake, actors, csir, _mapping = prepared(tmp_path)
    source = json.loads(csir.read_text(encoding="utf-8"))
    source["entities"].append({
        "entity_id": "helper", "name": "Helper", "ced_type": "entity.prop",
        "parent_entity_id": "hero",
    })
    source["entities"][1]["parent_entity_id"] = "helper"
    _write(csir, source)
    manifest_path = candidate / "automatic-setup.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_csir_sha256"] = AUDIT._sha(csir)
    _write(manifest_path, manifest)
    actors[1].parent = None
    result = AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)
    assert result["status"] == "INCOMPLETE"
    assert result["direct_edges_expected"] == 0
    assert len(result["unresolved_source_parents"]) == 1
    assert any("SOURCE_PARENT_NOT_MAPPED_AS_ACTOR" in x for x in result["incomplete"])


def test_source_content_drift_never_gets_reported_as_saved_parity(tmp_path):
    jobfile, candidate, fake, _actors, csir, _mapping = prepared(tmp_path)
    source = json.loads(csir.read_text(encoding="utf-8"))
    source["entities"][1]["name"] = "CAM_CHANGED"
    _write(csir, source)
    with pytest.raises(AUDIT.HierarchyAuditError, match="Stale or unverified source evidence"):
        AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)
    assert not (candidate / "hierarchy.json").exists()


def test_mapping_label_conflicts_are_refused(tmp_path):
    jobfile, candidate, fake, _actors, _csir, mapping = prepared(tmp_path)
    mapping_data = json.loads(mapping.read_text(encoding="utf-8"))
    mapping_data["entities"]["CAM"]["actor_label"] = "CSAI_Unrelated"
    _write(mapping, mapping_data)
    manifest_path = candidate / "automatic-setup.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mapping_sha256"] = AUDIT._sha(mapping)
    _write(manifest_path, manifest)
    with pytest.raises(AUDIT.HierarchyAuditError, match="Actor identity differs"):
        AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)


def test_duplicate_real_unreal_actors_are_not_passed(tmp_path):
    jobfile, candidate, fake, actors, _csir, _mapping = prepared(tmp_path)
    actors.append(Actor("CSAI_CAM"))
    result = AUDIT.audit(jobfile, candidate / "hierarchy.json", unreal_api=fake)
    assert result["status"] == "FAIL"
    assert any("MISSING_OR_DUPLICATE_MAPPED_ACTOR" in x for x in result["errors"])
