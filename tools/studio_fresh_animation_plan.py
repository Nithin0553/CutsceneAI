"""CutSceneAI: audited, standalone Stage 2 animation trial planning.

No engine writes. Every target Skeleton comes from a persisted Stage 1 audit,
never from a guessed asset name. Explicit assignments are operator-reviewed
trial choices, NOT evidence of rig compatibility or motion parity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
import studio_fresh_target_assets as stage1

KIND = 'cutsceneai.studio.fresh_animation_trial_plan'
SAFE_COMPONENT = re.compile(r'^[A-Za-z0-9_]+$')


class Stage2Error(ValueError):
    pass


def _read(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise Stage2Error(f'Expected object: {path}')
    return data


def _digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _target_folder(folder, stage1_folder):
    if not folder.startswith(stage1_folder + '/Animations_'):
        raise Stage2Error('Trial folder must be an Animations_ subfolder of the Stage 1 target namespace.')
    if any(not SAFE_COMPONENT.fullmatch(part) for part in folder.split('/')[2:]):
        raise Stage2Error('Unreal target folder has invalid component.')
    return folder


def compose(stage1_manifest, stage1_receipt, stage1_audit, assignments_file,
            target_folder, expected_level):
    paths = [Path(x).resolve() for x in (stage1_manifest, stage1_receipt, stage1_audit, assignments_file)]
    manifest_path, receipt_path, audit_path, assignment_path = paths
    stage = stage1.verify(manifest_path)
    receipt, audit, assignments = (_read(receipt_path), _read(audit_path), _read(assignment_path))
    if receipt.get('kind') != 'cutsceneai.studio.fresh_target_asset_import_receipt' or receipt.get('status') != 'IMPORTED_ASSETS_UNVERIFIED':
        raise Stage2Error('Stage 1 importer receipt not successful.')
    if receipt.get('manifest_sha256') != _digest(manifest_path):
        raise Stage2Error('Stage 1 manifest changed after import.')
    if Path(receipt.get('manifest_path', '')).resolve() != manifest_path:
        raise Stage2Error('Receipt does not reference the selected manifest.')
    if receipt.get('verified_project', '').casefold() != stage['target_project'].casefold():
        raise Stage2Error('Receipt target project differs from Stage 1 plan.')
    if audit.get('kind') != 'cutsceneai.studio.fresh_target_persistence_audit' or audit.get('status') != 'PERSISTED_ASSETS_AND_SKELETONS_READBACK':
        raise Stage2Error('Stage 1 persistence audit incomplete.')
    if Path(audit.get('receipt_path', '')).resolve() != receipt_path:
        raise Stage2Error('Audit is not linked to Stage 1 import receipt.')
    if audit.get('unreal_project', '').casefold() != stage['target_project'].casefold():
        raise Stage2Error('Audit target project differs from Stage 1 plan.')
    if not all(audit.get(k) is True for k in ('all_assets_readback', 'all_packages_saved',
                                             'skeletal_meshes_have_skeletons', 'skeleton_packages_saved')):
        raise Stage2Error('Stage 1 persistence has not been verified.')
    if not expected_level.startswith('/Game/') or not expected_level.strip('/').split('/')[-1]:
        raise Stage2Error('A saved /Game/... target level is required.')
    _target_folder(target_folder, stage['target_folder'])

    source_models = [r for r in stage['files'] if r['role'] == 'CHARACTER_MODEL' and
                     r['status'] == 'CANDIDATE_SKELETAL_MODEL_UNVERIFIED']
    imports = {r['target_asset_path']: r for r in receipt.get('imported', [])}
    audit_rows = {r['target_asset_path']: r for r in audit.get('rows', [])}
    models = {}
    for row in source_models:
        target = row['target_asset_path']
        imported, persisted = imports.get(target), audit_rows.get(target)
        if (not imported or imported.get('target_class') != 'SkeletalMesh' or
            not persisted or not persisted.get('class_matches') or not persisted.get('package_file_exists') or
            not persisted.get('skeleton_package_file_exists')):
            raise Stage2Error('Imported model or its Skeleton not verified: ' + str(target))
        skeleton = persisted.get('skeleton_asset_path')
        if not isinstance(skeleton, str) or not skeleton.startswith('/Game/'):
            raise Stage2Error('No verified skeleton path: ' + target)
        basename = Path(row['source_path']).name
        if basename in models:
            raise Stage2Error('Ambiguous model basename: ' + basename)
        models[basename] = {'skeleton_path': skeleton, 'mesh_path': target}

    animation_rows = [r for r in stage['files'] if r['role'] == 'ANIMATION_FBX'
                      and r['status'] == 'DEFERRED_SKELETON_COMPATIBILITY']
    if not animation_rows:
        raise Stage2Error('Stage 1 plan has no animation candidates.')
    names = [Path(r['source_path']).name for r in animation_rows]
    if len(names) != len(set(names)) or set(assignments) != set(names):
        raise Stage2Error('Each unique source animation filename must have one explicit assignment.')
    if any(v not in models for v in assignments.values()):
        raise Stage2Error('Assignment references a character model absent from verified Stage 1 assets.')

    entries = []
    seen = set()
    for row in sorted(animation_rows, key=lambda r: r['source_path']):
        name = Path(row['source_path']).name
        chosen = assignments[name]
        source_path = Path(row['source_file'])
        if not source_path.is_file() or _digest(source_path) != row['sha256']:
            raise Stage2Error('Source animation FBX changed or missing: ' + str(source_path))
        ident = re.sub(r'[^A-Za-z0-9_]', '_', source_path.stem).strip('_')
        dest = target_folder + '/CSAI_' + ident[:42] + '_' + row['sha256'][:10]
        if dest.lower() in seen:
            raise Stage2Error('Duplicate trial animation destination.')
        seen.add(dest.lower())
        entries.append({
            'source_file': str(source_path.resolve()), 'source_path': row['source_path'],
            'source_sha256': row['sha256'], 'target_asset_path': dest,
            'assigned_model_source': chosen,
            'target_skeleton_path': models[chosen]['skeleton_path'],
            'target_mesh_path': models[chosen]['mesh_path'],
            'assignment_confirmed_by_unreal': False,
            'animation_bone_compatibility_verified': False,
        })
    return {
        'kind': KIND, 'schema_version': '0.1.0',
        'stage1_manifest': str(manifest_path), 'stage1_manifest_sha256': _digest(manifest_path),
        'stage1_receipt': str(receipt_path), 'stage1_receipt_sha256': _digest(receipt_path),
        'stage1_audit': str(audit_path), 'stage1_audit_sha256': _digest(audit_path),
        'assignments_path': str(assignment_path), 'assignments_sha256': _digest(assignment_path),
        'target_project': stage['target_project'], 'target_level': expected_level,
        'target_folder': target_folder, 'animations': entries,
        'engine_import_executed': False, 'rig_compatibility_verified': False,
        'fidelity_verified': False,
        'warnings': [
            'Assignments are hypotheses from source cutscene semantics, not verified retargeting or bone compatibility.',
            'Native FBX animation import may be unsupported by this Unreal Editor runtime; report failures without retrying into an occupied folder.',
            'Actor setup, material parity, audio and cutscene generation are not performed.',
        ]}


def verify(plan_path):
    saved = _read(plan_path)
    if saved.get('kind') != KIND or saved.get('schema_version') != '0.1.0':
        raise Stage2Error('Unknown Stage 2 plan format.')
    for key, ref in (('stage1_manifest_sha256', 'stage1_manifest'),
                     ('stage1_receipt_sha256', 'stage1_receipt'),
                     ('stage1_audit_sha256', 'stage1_audit'),
                     ('assignments_sha256', 'assignments_path')):
        if _digest(saved[ref]) != saved[key]:
            raise Stage2Error('Stage 2 input modified: ' + ref)
    expected = compose(saved['stage1_manifest'], saved['stage1_receipt'], saved['stage1_audit'],
                       saved['assignments_path'], saved['target_folder'], saved['target_level'])
    if saved != expected:
        raise Stage2Error('Stage 2 plan changed or is stale. Create a new trial.')
    return saved


def main():
    p = argparse.ArgumentParser(description='CutSceneAI guarded animation trial planning (read-only)')
    sub = p.add_subparsers(dest='cmd', required=True)
    plan = sub.add_parser('plan')
    for opt in ('stage1-manifest', 'stage1-receipt', 'stage1-audit', 'assignments', 'target-folder', 'level', 'out'):
        plan.add_argument('--' + opt, required=True)
    check = sub.add_parser('verify')
    check.add_argument('--plan', required=True)
    a = p.parse_args()
    try:
        if a.cmd == 'plan':
            out = Path(a.out)
            if out.exists() or out.is_symlink():
                raise Stage2Error('Refusing to overwrite a Stage 2 trial plan.')
            data = compose(a.stage1_manifest, a.stage1_receipt, a.stage1_audit,
                           a.assignments, a.target_folder, a.level)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open('x', encoding='utf-8', newline='\n') as f:
                f.write(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + '\n')
        else:
            data = verify(a.plan)
        print('[CutSceneAI] STAGE 2 PLAN VERIFIED: ', len(data['animations']), 'animation trials')
        print('[CutSceneAI] Target folder:', data['target_folder'])
        print('[CutSceneAI] Unreal has not been modified; bone/motion compatibility UNVERIFIED.')
        return 0
    except (Stage2Error, stage1.FreshTargetError, OSError, ValueError, KeyError, TypeError) as exc:
        print('[CutSceneAI] STAGE 2 BLOCKED:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
