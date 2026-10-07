"""The initial command interface; socket operations are planned in PLAN.md."""

import argparse
import sys
from importlib.metadata import version


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="herdr-next-to-current",
        description="Open a Herdr tab or workspace beside the current item (initial scaffold).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {version('herdr-next-to-current')}",
    )
    resources = parser.add_subparsers(dest="resource", required=True)
    for resource in ("workspace", "tab"):
        command = resources.add_parser(
            resource, help=f"Create a {resource} immediately after the current {resource}"
        )
        command.add_argument("--label", metavar="TEXT", help="Name the new item")
        command.add_argument("--cwd", metavar="PATH", help="Set the initial working directory")
        command.add_argument("--no-focus", action="store_true", help="Keep the existing focus")
    args = parser.parse_args()
    print(
        f"herdr-next-to-current: {args.resource} creation is not implemented in this scaffold; "
        "see PLAN.md for the implementation plan.",
        file=sys.stderr,
    )
    return 2
