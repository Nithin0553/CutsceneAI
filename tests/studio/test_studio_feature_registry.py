"""Prevent silent loss/unsupported-action overclaims in capability audits."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'tools'))
import studio_feature_registry as catalog


def test_families_cover_major_game_cinematic_domains():
    assert len(catalog.FAMILIES) >= 16
    assert {'camera','skeletal','facial','materials','fx','narrative','simulation','custom','audio'} <= set(catalog.FAMILIES)


def test_unknown_track_survives_audit_instead_of_being_dropped():
    csir={'source':{'engine':'unity'},'cutscene_id':'c1',
          'entities':[{'name':'Hero','ced_type':'entity.character','entity_id':'a'}],
          'tracks':[{'name':'MyVendorTrack','ced_type':'vendor.custom_cinematic',
                     'sections':[{'ced_type':'vendor.plugin_clip'}]}]}
    plan={'actions':[{'kind':'skeletal_animation'},{'kind':'plugin.unknown_runtime'}]}
    data=catalog.audit(csir,plan)
    assert len(data['source_inventory']) == 3
    assert any(x['ced_type']=='vendor.custom_cinematic' for x in data['source_inventory'])
    assert data['family_counts']['custom'] == 2
    assert data['unimplemented_action_kinds']==['plugin.unknown_runtime']
    assert data['complete_cutscene_fidelity_verified'] is False
    assert all(not x['implementation_verified'] for x in data['families'].values())


def test_actual_builder_action_names_are_registered():
    assert {'camera_setup','camera_cut','skeletal_animation','audio','marker','light_intensity','transform'} <= catalog.CURRENT_BUILDER_ACTIONS
