"""Cross-runtime floating-point precision regression for CutSceneAI Stage 4."""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import studio_stage4_layout as stage4


def sample_plan():
    return {
        'kind': 'cutsceneai.studio.stage4_source_scene_layout_plan',
        'source_csir_sha256': 'fixed_hash',
        'target_level': '/Game/CutSceneAI/Tests/L_NewTarget_Test01',
        'hierarchy': {'attachments': [{'entity_name': 'PROP_PARENTED', 'source_parent_name': 'PROP_MOVING'}]},
        'placements': [{
            'actor_label': 'CAM_C_Close',
            'entity_name': 'CAM_C_Close',
            'source': 'entity.world_transform',
            'location_cm': [1240.216064453125, -168.29500198364258, 179.99999523162842],
            'rotation_rpy_degrees': [2.46919419383434e-08, -3.99999928226301, 154.8000032040623],
            'scale_xyz': [1.0, 1.0, 1.0],
        }],
    }


def test_ignores_last_bit_unreal_rotation_noise():
    saved = sample_plan()
    actual = copy.deepcopy(saved)
    actual['placements'][0]['rotation_rpy_degrees'] = [
        2.4691942833116495e-08, -3.999999282263009, 154.80000320406234,
    ]
    assert stage4._same_plan(saved, actual)


@pytest.mark.parametrize('name', ['location_cm', 'rotation_rpy_degrees', 'scale_xyz'])
def test_rejects_meaningful_pose_changes(name):
    saved = sample_plan()
    actual = copy.deepcopy(saved)
    actual['placements'][0][name][0] += 1e-5
    assert not stage4._same_plan(saved, actual)


def test_exact_hierarchy_and_actor_bindings():
    saved = sample_plan()
    actual = copy.deepcopy(saved)
    actual['placements'][0]['actor_label'] = 'OTHER'
    assert not stage4._same_plan(saved, actual)
    actual = copy.deepcopy(saved)
    actual['hierarchy']['attachments'] = []
    assert not stage4._same_plan(saved, actual)


def test_no_acceptance_of_nonfinite_or_boolean_poses():
    saved = sample_plan()
    actual = copy.deepcopy(saved)
    actual['placements'][0]['scale_xyz'][0] = float('nan')
    assert not stage4._same_plan(saved, actual)
    actual = copy.deepcopy(saved)
    actual['placements'][0]['scale_xyz'][0] = True
    assert not stage4._same_plan(saved, actual)
