"""Regression tests for source-driven albedo restoration (no Unreal Editor required)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "integrations" / "unreal"))
import studio_auto_assets
import studio_material_restore
from test_studio_auto_assets import create


def test_source_guid_material_is_planned_and_tamper_detected(tmp_path):
    project, docs = create(tmp_path)
    directory = project / "Assets" / "Benchmark002" / "Characters"
    texture = directory / "Body.png"
    texture.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    (directory / "Body.png.meta").write_text(
        "fileFormatVersion: 2\nguid: abcdef0123456789abcdef0123456789\n"
    )
    material = directory / "Body.mat"
    material.write_text(
        "Material:\n  m_SavedProperties:\n    m_TexEnvs:\n"
        "    - _BaseMap:\n        m_Texture: {fileID: 2800000, guid: abcdef0123456789abcdef0123456789, type: 3}\n"
    )
    source = json.loads(docs[0].read_text())
    source['entities'][0]['metadata'] = {'source_material_assets': [{
        'asset_path': material.relative_to(project).as_posix(),
        'albedo_texture_asset_path': texture.relative_to(project).as_posix(),
        'albedo_texture_guid': 'abcdef0123456789abcdef0123456789',
    }]}
    docs[0].write_text(json.dumps(source))
    plan = studio_auto_assets.inspect(
        *docs, project, "Assets/Benchmark002", "/Game/CutSceneAI/AutoTransfer/T_GUID"
    )
    assert plan["ready"]
    assert len(plan["source_albedo_material_candidates"]) == 1
    candidate = plan["source_albedo_material_candidates"][0]
    assert candidate["slot_name"] == "Body"
    assert candidate["target_texture"].startswith("/Game/")
    assert candidate["fidelity_verified"] is False
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(plan))
    assert studio_auto_assets.verify(manifest, *docs) == plan
    material.write_text(material.read_text() + "\n# source edited")
    import pytest
    with pytest.raises(studio_auto_assets.AutoAssetError, match="changed"):
        studio_auto_assets.verify(manifest, *docs)


def test_ambiguous_material_name_never_gets_guessed(tmp_path):
    project, docs = create(tmp_path)
    root = project / "Assets" / "Benchmark002"
    for folder in ("Characters", "Animations"):
        target = root / folder
        (target / "Body.mat").write_text(
            "    - _MainTex:\n        m_Texture: {fileID: 2800000, guid: abcdef0123456789abcdef0123456789, type: 3}\n"
        )
    source = json.loads(docs[0].read_text())
    source['entities'][0]['metadata'] = {'source_material_assets': [
        {'asset_path': (root / folder / 'Body.mat').relative_to(project).as_posix()}
        for folder in ('Characters', 'Animations')]}
    docs[0].write_text(json.dumps(source))
    result = studio_auto_assets.inspect(
        *docs, project, "Assets/Benchmark002", "/Game/CutSceneAI/AutoTransfer/T_GUID"
    )
    assert result["source_albedo_material_candidates"] == []
    assert result["source_albedo_actor_candidates"]["Ch31_nonPBR"] == []
    assert any("Ambiguous Unity material name" in x for x in result["warnings"])


def test_exact_renderer_material_and_texture_outside_scan_scope(tmp_path):
    project, docs = create(tmp_path)
    shared = project / 'Assets' / 'SharedMaterials'
    shared.mkdir()
    texture = shared / 'Body.png'
    texture.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
    texture_guid = 'abcdef0123456789abcdef0123456789'
    texture.with_name(texture.name + '.meta').write_text('guid: '+texture_guid+'\n')
    material = shared / 'Body.mat'
    material.write_text('    - _BaseMap:\n        m_Texture: {fileID: 2800000, guid: '+
                        texture_guid+', type: 3}\n')
    material_guid = '1234567890abcdef1234567890abcdef'
    material.with_name(material.name + '.meta').write_text('guid: '+material_guid+'\n')
    csir = json.loads(docs[0].read_text())
    csir['entities'][0]['metadata'] = {'source_material_assets': [{
        'asset_path': material.relative_to(project).as_posix(), 'guid': material_guid,
        'albedo_texture_asset_path': texture.relative_to(project).as_posix(),
        'albedo_texture_guid': texture_guid,
    }]}
    docs[0].write_text(json.dumps(csir))
    plan = studio_auto_assets.inspect(
        *docs, project, 'Assets/Benchmark002', '/Game/CutSceneAI/AutoTransfer/T_GUID'
    )
    assert plan['ready']
    assert len(plan['source_albedo_material_candidates']) == 1
    assert plan['source_albedo_material_candidates'][0]['source_texture'] == str(texture)
    assert any(row['source_file'] == str(texture) and row['kind'] == 'Texture2D'
               for row in plan['imports'])


class FakeMaterial:
    def __init__(self, path):
        self.path = path
    def get_path_name(self):
        return self.path


class FakeMesh:
    def get_editor_property(self, name):
        if name == "materials":
            return [SimpleNamespace(get_editor_property=lambda p: "Body")]
        raise AttributeError(name)


class FakeComponent:
    def __init__(self, material):
        self.material = material
        self.assignments = []
    def get_editor_property(self, name):
        if name == "skeletal_mesh_asset":
            return FakeMesh()
        raise AttributeError(name)
    def get_material(self, index):
        return self.material
    def set_material(self, index, material):
        self.assignments.append((index, material))


def _restore(component, candidates):
    class API:
        SkeletalMeshComponent = "SkeletalMeshComponent"
        StaticMeshComponent = "StaticMeshComponent"
    actor = SimpleNamespace(get_components_by_class=lambda cls: [component] if cls == "SkeletalMeshComponent" else [])
    return studio_material_restore.restore(API, actor, candidates)


def test_existing_custom_material_is_never_overwritten():
    component = FakeComponent(FakeMaterial("/Game/User/ExistingMat"))
    result = _restore(component, [{"slot_name": "Body"}])
    assert result[0]["status"] == "EXISTING_NONDEFAULT_PRESERVED"
    assert component.assignments == []


def test_unmatched_and_ambiguous_slots_preserve_worldgrid():
    component = FakeComponent(FakeMaterial("/Engine/EngineMaterials/WorldGridMaterial"))
    source = {"slot_name": "Body"}
    assert _restore(component, [source, source])[0]["status"] == "NO_UNIQUE_SOURCE_MATERIAL_MATCH"
    assert _restore(component, [dict(source, slot_name="Other")])[0]["status"] == "NO_UNIQUE_SOURCE_MATERIAL_MATCH"
    assert component.assignments == []


def test_static_mesh_source_material_matches_unreal_static_materials():
    """StaticMesh.materials is not its native slot property in Unreal."""
    class StaticMesh:
        def get_editor_property(self, name):
            if name == "materials":
                raise AttributeError("StaticMesh has no materials property")
            if name == "static_materials":
                return [SimpleNamespace(get_editor_property=lambda p: "Body"
                                        if p == "material_slot_name" else None)]
            raise AttributeError(name)

    class StaticComponent:
        def __init__(self):
            self.assigned = []
        def get_editor_property(self, name):
            if name == "static_mesh":
                return StaticMesh()
            raise AttributeError(name)
        def get_material(self, index):
            return FakeMaterial("/Engine/EngineMaterials/WorldGridMaterial")
        def set_material(self, index, material):
            self.assigned.append((index, material))

    component = StaticComponent()
    target_material = FakeMaterial("/Game/CutSceneAI/AutoTransfer/Materials/M_Body")
    source = {"slot_name": "Body",
              "target_material": "/Game/CutSceneAI/AutoTransfer/Materials/M_Body",
              "source_material_sha256": "a" * 64}
    class API:
        SkeletalMeshComponent = "SkeletalMeshComponent"
        StaticMeshComponent = "StaticMeshComponent"

    actor = SimpleNamespace(
        get_components_by_class=lambda cls:
        [component] if cls == "StaticMeshComponent" else [])
    rows = studio_material_restore.restore(
        API, actor, [source], existing_assets={source["target_material"]: target_material}
    )
    assert component.assigned == [(0, target_material)]
    assert rows[0]["status"] == "SOURCE_ALBEDO_ASSIGNED_RENDER_PARITY_UNVERIFIED"
    assert rows[0]["source_material_sha256"] == source["source_material_sha256"]


def _two_actors_with_same_slot(tmp_path):
    """Two source actors have identically named slots but different GUIDs."""
    project, docs = create(tmp_path)
    source = json.loads(docs[0].read_text())
    sources = {}
    for index, entity in enumerate(source["entities"][:2]):
        actor = entity["name"]
        folder = project / "Assets" / "Benchmark002" / actor
        folder.mkdir()
        guid = f"{index + 1:032x}"
        png = folder / "Body.png"
        png.write_bytes(b"\\x89PNG\\r\\n\\x1a\\n" + bytes([index + 1]) * 16)
        png.with_name(png.name + ".meta").write_text("guid: " + guid + "\\n")
        material = folder / "Body.mat"
        material.write_text(
            "    - _BaseMap:\\n"
            f"        m_Texture: {{fileID: 2800000, guid: {guid}, type: 3}}\\n"
        )
        entity["metadata"] = {"source_material_assets": [{
            "asset_path": material.relative_to(project).as_posix(),
            "albedo_texture_asset_path": png.relative_to(project).as_posix(),
            "albedo_texture_guid": guid,
        }]}
        sources[actor] = str(material.resolve())
    docs[0].write_text(json.dumps(source))
    stage = studio_auto_assets.inspect(
        *docs, project, "Assets/Benchmark002", "/Game/CutSceneAI/AutoTransfer/T_MULTIACTOR"
    )
    return project, docs, stage, sources


def test_actor_scoped_same_named_materials_not_globally_guessed(tmp_path):
    _, docs, plan, sources = _two_actors_with_same_slot(tmp_path)
    assert plan["ready"] is True
    # The global name 'Body' is ambiguous; it cannot be selected at random.
    assert plan["source_albedo_material_candidates"] == []
    by_actor = plan["source_albedo_actor_candidates"]
    assert set(by_actor) == set(sources)
    for actor, material_path in sources.items():
        assert len(by_actor[actor]) == 1
        assert by_actor[actor][0]["source_material"] == material_path
        assert by_actor[actor][0]["slot_name"] == "Body"
        assert by_actor[actor][0]["fidelity_verified"] is False
    assert (by_actor["Ch31_nonPBR"][0]["target_texture"]
            != by_actor["Ch26_nonPBR"][0]["target_texture"])
    assert not any("Ambiguous Unity material name" in w for w in plan["warnings"])
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(plan))
    assert studio_auto_assets.verify(manifest, *docs) == plan


def test_native_setup_receives_only_the_matching_actor_source_material(tmp_path, monkeypatch):
    import studio_auto_scene as scene
    from test_studio_auto_scene import FakeUnreal

    _, docs, stage, sources = _two_actors_with_same_slot(tmp_path)
    manifest = tmp_path / "automatic-setup.json"
    manifest.write_text(json.dumps(stage))
    project = tmp_path / "Project.uproject"
    project.write_text("{}")
    api = FakeUnreal(str(project))
    invoked = []

    def record_restore(_api, actor, candidates, *, existing_assets=None):
        invoked.append((actor.get_actor_label(), [x["source_material"] for x in candidates]))
        return [{"slot_name": c["slot_name"], "status": "SOURCE_MATCH_ONLY_UNVERIFIED"}
                for c in candidates]

    monkeypatch.setattr(scene.studio_material_restore, "restore", record_restore)
    result = scene.run(
        str(manifest), str(tmp_path / "receipt.json"),
        csir_path=str(docs[0]), mapping_path=str(docs[1]), plan_path=str(docs[2]),
        expected_project=str(project), expected_level="/Game/Tests/L_Test", unreal_api=api,
    )
    assert result["status"] == "SETUP_SAVED_UNVERIFIED"
    expected_labels = {row["label"]: row["name"] for row in stage["actors"]}
    assert len(invoked) == 2
    for label, paths in invoked:
        assert paths == [sources[expected_labels[label]]]
    assert {x["actor"] for x in result["material_restoration"]} == set(sources)
    assert result["fidelity_verified"] is False
