"""Read-only CLI for reporting game-cinematic feature coverage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from studio_feature_registry import audit_files


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit cutscene source feature inventory')
    parser.add_argument('--csir', type=Path, required=True)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args(argv)
    data = audit_files(args.csir, args.plan)
    encoded = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    if args.out:
        if args.out.exists():
            parser.error('Refusing to overwrite existing feature inventory.')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(encoded, encoding='utf-8')
    print('Source feature items:', len(data['source_inventory']))
    print('Unknown native action kinds:', data['unimplemented_action_kinds'])
    print('Fidelity:', 'UNVERIFIED')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
