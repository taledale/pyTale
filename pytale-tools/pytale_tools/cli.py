"""CLI interface for pytale-tools"""

import argparse
import sys
from pathlib import Path

from pytale_tools.build import PluginBuilder


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser"""
    parser = argparse.ArgumentParser(
        prog="pytale-tools", description="PyTale development tools"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build a Python plugin JAR")
    build_parser.add_argument("wheel", type=Path, help="Path to wheel file (.whl)")
    build_parser.add_argument(
        "-o", "--output", type=Path, help="Output JAR path (default: plugin-name.jar)"
    )
    build_parser.add_argument(
        "-r",
        "--requirements",
        type=Path,
        help="Optional: path to requirements.txt for plugin dependencies (versions must be pinned with ==)",
    )
    build_parser.add_argument(
        "-c",
        "--cache-dir",
        type=Path,
        help="Optional: directory for caching downloaded wheels (default: .pytale/wheels in project or ~/.cache/pytale/wheels)",
    )

    return parser


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "build":
            builder = PluginBuilder(
                args.wheel,
                args.requirements,
                args.cache_dir if hasattr(args, "cache_dir") else None,
            )
            output = args.output or Path(f"{builder.metadata['name']}.jar")
            builder.build(output)
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
