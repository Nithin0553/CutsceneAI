# Studio supported-asset transfer — WAV vertical slice (Issue #80 B1/B2)

This implements a native Unreal import route, not just a name proposal. The supported source-file type is **project-local Unity AudioClip WAV**. Unity-native .anim, PlayableAsset, FBX skeletal animation, materials, shader graphs, prefabs, scripts, controllers and other formats are never silently converted. An imported SoundWave is *not* independently verified audio playback equivalence.

## Step 1 — prepare a read-only manifest

~~~powershell
python tools/studio_assets.py plan --csir "D:\source\scene.csir.json" --mapping "D:\session\mapping.json" --source-project "D:\UnityProject" --target-folder "/Game/CutSceneAI/StudioAssets_Run_001" --out "D:\session\assets-import-v1.json"
python tools/studio_assets.py verify --csir "D:\source\scene.csir.json" --mapping "D:\session\mapping.json" --manifest "D:\session\assets-import-v1.json"
~~~

Every referenced asset (including transitive metadata.dependency_asset_ids) is listed with status, source path, hash and prospective target. Source escapes, missing files/references, ambiguity and unsupported formats are preserved as coverage gaps. Only READY_WAV_IMPORT is a native importer candidate.

## Step 2 — run the opt-in importer in Unreal Editor

The user must confirm appropriate rights to transfer the source WAVs. Make a backup of the target Unreal project. Choose a unique, unused target content folder and new runtime receipt / mapping filenames:

~~~python
import sys
sys.path.insert(0, r"D:\CutSceneAI\integrations\unreal")
import stage_asset_import

receipt = stage_asset_import.run(
    r"D:\session\assets-import-v1.json",
    r"D:\source\scene.csir.json",
    r"D:\session\mapping.json",
    expected_project_path=r"D:\UnrealProject\UnrealProject.uproject",
    resolved_mapping_path=r"D:\session\mapping-imported-v1.json",
    runtime_receipt_path=r"D:\session\assets-import-receipt-v1.json",
    rights_confirmed=True,  # operator confirms source import rights
)
print(receipt["status"], receipt["imported"], receipt["blocked"])
~~~

The editor preflight verifies exact project path, source bytes, manifest, existing SoundWave types and all destination paths before mutation. Unreal AssetImportTask performs the actual import; each resulting object must load as SoundWave before being added to a **new** mapping file. Existing mappings are not overwritten. If an importer fails after beginning engine changes, the immutable failure receipt reports POSSIBLE_MUST_INSPECT; no unsafe forced asset deletion occurs. Inspect the editor state and use a new namespace to retry.

## Step 3 — produce a normal verified transfer plan

~~~powershell
python tools/studio_transfer.py prepare --csir "D:\source\scene.csir.json" --mapping "D:\session\mapping-imported-v1.json" --out "D:\session\transfer-v1" --target-project "D:\UnrealProject\UnrealProject.uproject" --asset-manifest "D:\session\assets-import-v1.json" --asset-receipt "D:\session\assets-import-receipt-v1.json" --asset-original-mapping "D:\session\mapping.json"
python tools/studio_transfer.py verify --out "D:\session\transfer-v1"
~~~

Studio now checks that the editor import receipt, original mapping, source WAV hashes and new target mapping are a consistent provenance chain; any later evidence edits block verification. This does not independently prove actual Unreal content persistence or playback.

Now use the existing build_level_sequence.build_prepared_files(...) in the target Unreal Editor using the resulting plan/report/evidence and fresh generation receipt. Validate the saved sequence with independent validate_transfer and CineTwin checks.

This importer does **not** spawn scene actors, retarget skeletons, invoke generation, or prove waveform/visual fidelity. GitHub CI tests use an Unreal mock; B1/B2 and CUT-02 remain open pending an authentic editor-native import, persistence/readback and independently authored source evidence.
