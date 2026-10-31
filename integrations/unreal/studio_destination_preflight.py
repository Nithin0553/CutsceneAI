"""Read-only destination readiness for the Studio Unreal generation handoff.

Checks *the actual loaded level* against all planned actor bindings and the
assets used by the immutable transfer plan. Does not fabricate actors or assets.
Runs in Unreal Editor via studio_local_editor_worker; pure assessment is
independently testable without an Unreal installation.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

ACTOR_ACTION_KINDS = {
    'camera_setup': 'camera', 'camera_fov': 'camera',
    'light_intensity': 'light', 'skeletal_animation': 'skeletal',
}
ASSET_KINDS = {'skeletal_animation': 'AnimSequence', 'audio': 'SoundWave'}


def assess(plan: dict[str, Any], actors: list[dict[str, Any]],
           assets: dict[str, dict[str, Any]], *, sequence_exists: bool,
           project_matches: bool, level_matches: bool) -> dict[str, Any]:
    """Report missing/ambiguous mapped actors and source-required Unreal assets.

    `actors` is an actual snapshot of loaded-level actors, never invented.
    `assets` is the asset-registry lookup indexed by planned Unreal asset path.
    No mutations occur here, and no stage success/fidelity is inferred.
    """
    bindings = plan.get('bindings') or {}
    if not isinstance(bindings, dict) or not bindings:
        raise ValueError('Prepared plan contains no target actor bindings.')
    actions = plan.get('actions') or []
    if not isinstance(actions, list):
        raise ValueError('Prepared actions must be a list.')
    names = Counter(str(row.get('label') or '') for row in actors)
    by_label = {str(row.get('label')): row for row in actors if names[str(row.get('label') or '')] == 1}
    kinds: dict[str, set[str]] = {}
    required_assets: dict[str, str] = {}
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError('Invalid prepared action.')
        kind = str(action.get('kind') or '')
        entity = str(action.get('entity_name') or '')
        if kind in ACTOR_ACTION_KINDS and entity:
            kinds.setdefault(entity, set()).add(ACTOR_ACTION_KINDS[kind])
        if kind in ASSET_KINDS:
            path = str(action.get('unreal_asset_path') or '')
            if not path.startswith('/Game/'):
                raise ValueError('Prepared action has missing or invalid Unreal asset path.')
            required_assets[path] = ASSET_KINDS[kind]
    missing_actors = []
    duplicate_actors = []
    wrong_actor_types = []
    for entity, label in bindings.items():
        label = str(label)
        count = names[label]
        row = {'entity_name': str(entity), 'actor_label': label}
        if count == 0:
            missing_actors.append(row)
        elif count > 1:
            duplicate_actors.append({**row, 'count': count})
        else:
            present = by_label[label]
            actual_kind = str(present.get('kind') or 'actor')
            expected_kinds = kinds.get(str(entity), set())
            for expected in sorted(expected_kinds):
                if actual_kind != expected:
                    wrong_actor_types.append({**row, 'expected': expected, 'actual': actual_kind})
    missing_assets = []
    wrong_asset_types = []
    for path, expected in sorted(required_assets.items()):
        actual = assets.get(path) or {}
        if not actual.get('exists'):
            missing_assets.append({'asset_path': path, 'expected_class': expected})
        elif actual.get('class_name') and actual['class_name'] != expected:
            wrong_asset_types.append({'asset_path': path, 'expected_class': expected,
                                      'actual_class': actual['class_name']})
    blocked = (
        not project_matches or not level_matches or sequence_exists
        or missing_actors or duplicate_actors or wrong_actor_types
        or missing_assets or wrong_asset_types
    )
    if not project_matches or not level_matches:
        status, next_action = 'WRONG_TARGET', 'Open the selected Unreal project and level.'
    elif sequence_exists:
        status, next_action = 'TARGET_EXISTS', 'Prepare a new transfer with a unique sequence name.'
    elif missing_assets or wrong_asset_types:
        status, next_action = 'ASSETS_REQUIRED', 'Import and map the listed Unreal assets before generation.'
    elif missing_actors or duplicate_actors or wrong_actor_types:
        status, next_action = 'SCENE_SETUP_REQUIRED', 'Create or correctly map the listed scene actors before generation.'
    else:
        status, next_action = 'READY', 'Destination prerequisites verified. You can generate a new Level Sequence.'
    return {
        'kind': 'cutsceneai.studio.destination_readiness',
        'schema_version': '0.1.0',
        'status': status, 'ready': not bool(blocked),
        'expected_actor_count': len(bindings),
        'found_actor_count': len(bindings) - len(missing_actors) - len(duplicate_actors),
        'required_asset_count': len(required_assets),
        'missing_actors': missing_actors,
        'duplicate_actors': duplicate_actors,
        'wrong_actor_types': wrong_actor_types,
        'missing_assets': missing_assets,
        'wrong_asset_types': wrong_asset_types,
        'sequence_exists': bool(sequence_exists),
        'project_matches': bool(project_matches),
        'level_matches': bool(level_matches),
        'next_action': next_action,
        'scene_modified': False,
        'target_fidelity_established': False,
    }
