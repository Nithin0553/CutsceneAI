"""CutSceneAI Stage 4: immutable scene pose/attachment plan; no Unreal import.

Consumes the independently audited Stage 3 target and the immutable Unity CSIR.
Uses the existing generic CSIR-to-Unreal math, never hard-coded transforms.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import ntpath
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
for folder in [ROOT / 'integrations' / 'unreal', ROOT / 'packages' / 'cinetwin']:
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

class LayoutError(ValueError):
    pass

def read(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict):
        raise LayoutError(f'Expected JSON object: {path}')
    return data

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def path_key(value):
    return ntpath.normcase(ntpath.normpath(str(value).replace('/', '\\')))

def new_json(path, obj):
    target = Path(path)
    if not target.parent.is_dir():
        raise LayoutError(f'Parent directory missing: {target.parent}')
    with target.open('x', encoding='utf-8', newline='\n') as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write('\n')

def _numeric(seq, size, label):
    if not isinstance(seq, (tuple, list)) or len(seq) != size:
        raise LayoutError(f'Invalid {label}: expected {size} numbers')
    result = [float(x) for x in seq]
    if not all(math.isfinite(x) for x in result):
        raise LayoutError(f'Nonfinite {label}')
    return result

def _candidate_from_first_transform(csir, mapping):
    """World-space first *timeline* key, only when its frame equals playback start."""
    import csir_plan
    entities = {str(e['entity_id']): e for e in csir.get('entities', [])}
    source_rate = csir['timing']['source_rate']
    n, d = int(source_rate['numerator']), int(source_rate['denominator'])
    start_seconds = csir_plan.rational_seconds(csir.get('timing', {}).get(
        'playback_start', {'value': 0, 'rate': {'numerator': 1, 'denominator': 1}}))
    start_frame = csir_plan.seconds_to_frame(start_seconds, n, d)
    dynamic = {}
    actions = []
    blockers = []
    for track in csir.get('tracks', []):
        if track.get('muted') is True:
            continue
        entity = entities.get(str(track.get('binding_entity_id', '')))
        if not entity or entity.get('name') not in mapping.get('entities', {}):
            continue
        # Only actual transform-bearing tracks. Not all animation tracks represent actor world motion.
        if track.get('ced_type') not in ('camera.transform', 'animation.track'):
            continue
        if track.get('ced_type') == 'animation.track' and entity.get('ced_type') == 'entity.character':
            continue
        try:
            action = csir_plan._transform_action(
                track, entity, mapping['entities'][entity['name']]['actor_label'], n, d, entities
            )
        except (ValueError, KeyError, TypeError) as exc:
            blockers.append(f"{entity['name']}: {exc}")
            continue
        if not action:
            continue
        actions.append(action)
        key = min(action['keys'], key=lambda x: int(x['frame']))
        name = entity['name']
        if name in dynamic:
            blockers.append(f'{name}: multiple world-transform tracks; initial placement ambiguous')
            dynamic.pop(name, None)
            continue
        if int(key['frame']) != start_frame:
            blockers.append(f'{name}: first authored transform frame {key["frame"]} != start frame {start_frame}')
            continue
        dynamic[name] = {
            'actor_label': action['actor_label'], 'entity_name': name,
            'kind': 'actor_transform', 'source': 'source_timeline_first_key',
            'location_cm': _numeric(key['location_cm'], 3, 'location_cm'),
            'rotation_rpy_degrees': _numeric(key['rotation_rpy_degrees'], 3, 'rotation_rpy_degrees'),
            'scale_xyz': None, 'frame': start_frame,
        }
    return dynamic, actions, blockers

def compose(stage3_plan_path, stage3_receipt_path, stage3_audit_path):
    import scene_prep
    plan3, receipt3, audit3 = map(read, (stage3_plan_path, stage3_receipt_path, stage3_audit_path))
    if plan3.get('kind') != 'cutsceneai.studio.stage3_scene_plan':
        raise LayoutError('Not a Stage 3 plan')
    if receipt3.get('kind') != 'cutsceneai.studio.stage3_scene_receipt' or receipt3.get('status') != 'ACTORS_CREATED_LEVEL_NOT_YET_VERIFIED':
        raise LayoutError('Stage 3 creation receipt is not ready')
    if audit3.get('kind') != 'cutsceneai.studio.stage3_scene_persistence_audit' or audit3.get('status') != 'STAGE3_SAVED_ACTORS_READBACK':
        raise LayoutError('Stage 3 persistent actor audit is not ready')
    if not (audit3.get('mapping_exists') and audit3.get('mapping_matches_plan')):
        raise LayoutError('Stage 3 mapping was not verified')
    if int(audit3.get('readback_count', -1)) != 8 or int(audit3.get('expected_count', -1)) != 8:
        raise LayoutError('Stage 3 actors did not persist completely')
    if not all(row.get('readback_ready') for row in audit3.get('rows', [])) or len(audit3.get('rows', [])) != 8:
        raise LayoutError('Some Stage 3 actor readbacks failed')
    if path_key(audit3['project']) != path_key(plan3['target_project']) or audit3['level'] != plan3['target_level']:
        raise LayoutError('Stage 3 audit targets a different project or level')
    if path_key(audit3.get('receipt_path', '')) != path_key(stage3_receipt_path):
        raise LayoutError('Stage 3 audit does not belong to the supplied receipt')
    if path_key(receipt3.get('plan_path', '')) != path_key(stage3_plan_path):
        raise LayoutError('Stage 3 creation receipt does not belong to the plan')
    if path_key(receipt3.get('mapping_path', '')) != path_key(plan3['mapping_output_path']):
        raise LayoutError('Stage 3 receipt mapping path mismatch')
    if len(receipt3['actors_created']) != 8:
        raise LayoutError('Stage 3 actor creation was incomplete')
    if sha(plan3['csir_path']) != plan3['csir_sha256']:
        raise LayoutError('Unity CSIR source changed since Stage 3')
    mapping = read(plan3['mapping_output_path'])
    if mapping != plan3['mapping']:
        raise LayoutError('Stage 3 mapping differs from verified plan')
    csir = read(plan3['csir_path'])
    try:
        ops = scene_prep.build_scene_prep(csir, mapping)
        dynamic, actions, warnings = _candidate_from_first_transform(csir, mapping)
    except Exception as exc:
        raise LayoutError('Failed source layout conversion: ' + str(exc)) from exc
    by_name = {}
    for op in ops:
        name = str(op['entity_name'])
        if name in by_name:
            raise LayoutError(f'Duplicate source-derived position: {name}')
        by_name[name] = {
            'kind': 'actor_transform', 'entity_name': name,
            'actor_label': str(op['actor_label']), 'source': str(op['source']),
            'location_cm': _numeric(op['location_cm'], 3, 'location_cm'),
            'rotation_rpy_degrees': _numeric((op['rotation_pitch_yaw_roll_degrees'][2],
                     op['rotation_pitch_yaw_roll_degrees'][0], op['rotation_pitch_yaw_roll_degrees'][1]), 3, 'rotation'),
            'scale_xyz': _numeric(op['scale_xyz'], 3, 'scale_xyz'),
        }
    # Timeline frame-zero keys supersede source editor placement for dynamic actors.
    by_name.update(dynamic)
    # Do not treat a dynamically-tracked actor with a missing first-frame pose as proven.
    blocked_names = {str(line).split(':', 1)[0] for line in warnings}
    for name in blocked_names:
        by_name.pop(name, None)
    required = {row['source_name']: row['actor_label'] for row in plan3['actors']}
    for name, op in by_name.items():
        if name not in required or op['actor_label'] != required[name]:
            raise LayoutError(f'Unexpected source mapping in position: {name}')
    missing = sorted(set(required) - set(by_name))
    hierarchy = {'attachments': [], 'parent_initializations': [], 'unresolved_source_parents': [], 'policy': 'NOT_APPLIED'}
    hierarchy_blocker = None
    try:
        import hierarchy_realization
        hierarchy = hierarchy_realization.build_attachment_operations(csir, mapping, actions)
    except Exception as exc:
        hierarchy_blocker = str(exc)
    # If any parent/child lacks an independently source-derived pose, refuse attachment.
    attach_labels = {e['entity_name'] for e in hierarchy['attachments']} | {e['source_parent_name'] for e in hierarchy['attachments']}
    if attach_labels - set(by_name):
        hierarchy_blocker = 'Some parent/child actors lack source-derived placements: ' + ', '.join(sorted(attach_labels - set(by_name)))
        hierarchy['attachments'] = []
        hierarchy['parent_initializations'] = []
    return {
        'kind': 'cutsceneai.studio.stage4_source_scene_layout_plan',
        'schema_version': '0.1.0',
        'target_project': plan3['target_project'], 'target_level': plan3['target_level'],
        'stage3_plan_path': str(Path(stage3_plan_path).resolve()), 'stage3_plan_sha256': sha(stage3_plan_path),
        'stage3_receipt_path': str(Path(stage3_receipt_path).resolve()), 'stage3_receipt_sha256': sha(stage3_receipt_path),
        'stage3_audit_path': str(Path(stage3_audit_path).resolve()), 'stage3_audit_sha256': sha(stage3_audit_path),
        'mapping_path': str(Path(plan3['mapping_output_path']).resolve()), 'mapping_sha256': sha(plan3['mapping_output_path']),
        'source_csir_path': str(Path(plan3['csir_path']).resolve()), 'source_csir_sha256': sha(plan3['csir_path']),
        'placements': [by_name[n] for n in sorted(by_name)], 'missing_source_poses': missing,
        'hierarchy': hierarchy, 'hierarchy_blocker': hierarchy_blocker,
        'source_transform_warnings': warnings,
        'generation_executed': False, 'level_modified': False, 'fidelity_verified': False,
        'cutscene_generated': False,
    }

# Only source-derived transform components may tolerate cross-runtime float noise.
# Positions are in cm, rotations in degrees, and scale is unitless. The absolute
# tolerance is far below any meaningful cutscene placement change.
_POSE_FIELDS = frozenset({'location_cm', 'rotation_rpy_degrees', 'scale_xyz'})
_POSE_REL_TOL = 1e-12
_POSE_ABS_TOL = 1e-9


def _same_pose_values(saved, recomputed):
    if saved is None or recomputed is None:
        return saved is None and recomputed is None
    if (not isinstance(saved, list) or not isinstance(recomputed, list)
            or len(saved) != 3 or len(recomputed) != 3):
        return False
    for a, b in zip(saved, recomputed):
        # bool is an int subclass; do not silently accept it as a pose number.
        if type(a) not in (int, float) or type(b) not in (int, float):
            return False
        if not math.isfinite(a) or not math.isfinite(b):
            return False
        if not math.isclose(a, b, rel_tol=_POSE_REL_TOL, abs_tol=_POSE_ABS_TOL):
            return False
    return True


def _same_placements(saved, recomputed):
    if not isinstance(saved, list) or not isinstance(recomputed, list):
        return False
    if len(saved) != len(recomputed):
        return False
    for a, b in zip(saved, recomputed):
        if not isinstance(a, dict) or not isinstance(b, dict) or a.keys() != b.keys():
            return False
        for key in a:
            if key in _POSE_FIELDS:
                if not _same_pose_values(a[key], b[key]):
                    return False
            elif a[key] != b[key]:
                return False
    return True


def _same_plan(saved, recomputed):
    if not isinstance(saved, dict) or not isinstance(recomputed, dict):
        return False
    if saved.keys() != recomputed.keys():
        return False
    # Exact equality for provenance, hashes, source IDs, actor assignments,
    # hierarchy/attachment operations, frames and all other plan fields.
    if any(saved[key] != recomputed[key] for key in saved if key != 'placements'):
        return False
    return _same_placements(saved['placements'], recomputed['placements'])


def verify(plan_path):
    p = read(plan_path)
    if p.get('kind') != 'cutsceneai.studio.stage4_source_scene_layout_plan' or p.get('schema_version') != '0.1.0':
        raise LayoutError('Not a supported Stage 4 plan')
    for path, digest in [('stage3_plan_path','stage3_plan_sha256'),('stage3_receipt_path','stage3_receipt_sha256'),('stage3_audit_path','stage3_audit_sha256'),('mapping_path','mapping_sha256'),('source_csir_path','source_csir_sha256')]:
        if sha(p[path]) != p[digest]:
            raise LayoutError('Stale source input: ' + path)
    expected = compose(p['stage3_plan_path'], p['stage3_receipt_path'], p['stage3_audit_path'])
    if not _same_plan(p, expected):
        raise LayoutError('Stage 4 plan does not match independently recomputed source state')
    return p

def main():
    arg = argparse.ArgumentParser()
    sub = arg.add_subparsers(dest='command', required=True)
    p = sub.add_parser('plan')
    p.add_argument('--stage3-plan', required=True)
    p.add_argument('--stage3-receipt', required=True)
    p.add_argument('--stage3-audit', required=True)
    p.add_argument('--out', required=True)
    v = sub.add_parser('verify')
    v.add_argument('--plan', required=True)
    a = arg.parse_args()
    try:
        if a.command == 'plan':
            result = compose(a.stage3_plan, a.stage3_receipt, a.stage3_audit)
            new_json(a.out, result)
        else:
            result = verify(a.plan)
        print('[CutSceneAI] STAGE 4 SOURCE LAYOUT PLAN VERIFIED')
        print('[CutSceneAI] Source-derived placements:', len(result['placements']), '/ 8')
        print('[CutSceneAI] Missing source poses:', result['missing_source_poses'])
        print('[CutSceneAI] Planned attachments:', len(result['hierarchy']['attachments']))
        print('[CutSceneAI] Hierarchy blocker:', result['hierarchy_blocker'])
        print('[CutSceneAI] No Unreal changes; source/target fidelity unverified.')
    except Exception as exc:
        print('[CutSceneAI] STAGE 4 BLOCKED:', exc, file=sys.stderr)
        sys.exit(2)

if __name__ == '__main__':
    main()
