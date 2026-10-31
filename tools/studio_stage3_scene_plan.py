"""CutSceneAI Stage 3 scene mapping planner. Does not load Unreal."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'integrations' / 'unreal'))
import studio_stage3_scene as s


def main(argv=None):
    p = argparse.ArgumentParser(description='Read-only Stage 3 actor staging plan')
    actions = p.add_subparsers(dest='action', required=True)
    prepare = actions.add_parser('plan')
    for key in ('csir', 'stage1-receipt', 'stage2-receipt', 'stage2-audit',
                'project', 'level', 'out', 'mapping-out'):
        prepare.add_argument('--' + key, required=True)
    check = actions.add_parser('verify')
    check.add_argument('--plan', required=True)
    args = p.parse_args(argv)
    try:
        if args.action == 'plan':
            report = s.plan(csir_path=args.csir, stage1_receipt_path=args.stage1_receipt,
                            stage2_receipt_path=args.stage2_receipt, stage2_audit_path=args.stage2_audit,
                            expected_project_path=args.project, target_level=args.level,
                            output_path=args.out, mapping_output_path=args.mapping_out)
            print('[CutSceneAI] STAGE 3 SCENE PLAN:', args.out)
        else:
            report = s.verify(args.plan)
            print('[CutSceneAI] STAGE 3 SCENE PLAN VERIFIED:', len(report['actors']), 'actors')
        print('[CutSceneAI] Source entities staged:', [x['source_name'] for x in report['actors']])
        print('[CutSceneAI] Actual Unreal level UNMODIFIED. Scene fidelity UNVERIFIED.')
        return 0
    except (s.SceneStageError, ValueError, OSError, KeyError) as exc:
        print('[CutSceneAI] STAGE 3 BLOCKED:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
