#!/usr/bin/env python3
"""Headless single-file conversion with the same atomic engine as the GUI."""
import argparse
import json
from pathlib import Path
from fluxfile import Engine, resolve_output


def main():
    parser = argparse.ArgumentParser(description='FluxFile local file converter')
    parser.add_argument('source', nargs='?', type=Path)
    parser.add_argument('--to', help='Target format, for example mp3, png, docx or tgz')
    parser.add_argument('--output-dir', type=Path, default=Path('converted'))
    parser.add_argument('--conflict', choices=['suffix', 'skip', 'overwrite'], default='suffix')
    parser.add_argument('--engines', action='store_true', help='Print installed engine availability')
    args = parser.parse_args()
    engine = Engine()
    if args.engines:
        print(json.dumps(engine.capabilities(), indent=2))
        return 0
    if not args.source or not args.to:
        parser.error('source and --to are required unless --engines is used')
    if not args.source.is_file():
        parser.error('source must be an existing file')
    target = args.to.lower().lstrip('.')
    if not target.isalnum():
        parser.error('target must be a format name, not a path')
    output = resolve_output(args.source, args.output_dir, target, args.conflict)
    if output is None:
        print('Skipped: output exists')
        return 0
    try:
        used = engine.convert(args.source, output)
    except Exception as exc:
        print(f'Conversion failed: {exc}')
        return 1
    print(f'{used}: {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
