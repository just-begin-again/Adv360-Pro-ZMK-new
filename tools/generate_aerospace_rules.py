#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from host.adv360_host import generate_aerospace_fragment


DEFAULT_MANIFEST = ROOT / "host" / "symbols" / "manifest.json"
DEFAULT_OUTPUT = ROOT / "host" / "karabiner" / "adv360-aerospace.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".aerospace.toml",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        manifest = json.loads(args.manifest.read_text())
        config = args.config.read_text()
        content = (
            json.dumps(
                generate_aerospace_fragment(config, manifest),
                indent=2,
                ensure_ascii=False,
            )
            + "\n"
        )
        if args.check:
            if not args.output.is_file() or args.output.read_text() != content:
                raise ValueError(f"generated file differs: {args.output}")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
