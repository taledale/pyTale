"""CLI interface for pytale-tools"""

import argparse
import sys
from pathlib import Path

from .build import PluginBuilder


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser"""
    parser = argparse.ArgumentParser(
        prog="pytale-tools",
        description="PyTale development tools"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Build command
    build_parser = subparsers.add_parser("build", help="Build a Python plugin JAR")
    build_parser.add_argument("wheel", type=Path, help="Path to wheel file (.whl)")
    build_parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output JAR path (default: plugin-name.jar)"
    )

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "build":
            builder = PluginBuilder(args.wheel)
            output = args.output or Path(f"{builder.metadata['name']}.jar")
            builder.build(output)
            return 0
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
