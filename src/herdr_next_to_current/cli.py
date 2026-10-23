"""Command interface and durable diagnostics for detached shortcuts."""

import argparse
import fcntl
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from .client import Client, ClientError
from .placement import Outcome, PlacementError, capture, create_after, move_before
from .tabs import capture_tab, create_tab_after


def failure_log(outcome):
    directory = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    directory /= "herdr-next-to-current"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "failures.log"
    record = {"time": datetime.now(UTC).isoformat(), **asdict(outcome)}
    # Preserve valid JSON even for oversized server errors or caller-provided IDs.
    record = {
        key: value[:1000] if isinstance(value, str) else value for key, value in record.items()
    }
    line = json.dumps(record, ensure_ascii=True) + "\n"
    with (directory / "diagnostics.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists() and path.stat().st_size + len(line) > 65536:
            path.replace(directory / "failures.log.1")
        with path.open("a", encoding="utf-8") as log:
            log.write(line)
    return path


def report_failure(client, outcome, resource="Space"):
    try:
        path = failure_log(outcome)
    except OSError as error:
        print(f"could not write failure log: {error}", file=sys.stderr)
        return
    if client is not None:
        try:
            client.call(
                "notification.show",
                {"title": f"{resource} operation failed", "body": f"{outcome.error}\nLog: {path}"},
                "notification_show",
                mutation=True,
            )
        except ClientError:
            pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise PlacementError(message, stage="usage")


def nonempty(value):
    if not value:
        raise argparse.ArgumentTypeError("must not be empty")
    return value


def parser():
    root = ArgumentParser(
        prog="herdr-next-to-current",
        description="Create and order Herdr Spaces and tabs beside the caller.",
    )
    root.add_argument(
        "--version", action="version", version=f"%(prog)s {version('herdr-next-to-current')}"
    )
    root.add_argument("--socket", type=nonempty, metavar="PATH", help="Requires an explicit source")
    root.add_argument(
        "--source-workspace", type=nonempty, metavar="ID", help="Pin the source Space"
    )
    root.add_argument(
        "--source-tab", type=nonempty, metavar="ID", help="Pin the source tab (tab only)"
    )
    commands = root.add_subparsers(dest="resource", required=True)
    for resource in ("workspace", "tab"):
        command = commands.add_parser(resource, help=f"Create an adjacent {resource}")
        command.add_argument("--label")
        command.add_argument("--cwd")
        command.add_argument("--no-focus", action="store_true")
        command.add_argument("--json", action="store_true")
        command.add_argument("--quiet", action="store_true", help="Suppress successful output")
    command = commands.add_parser("reorder", help="Move the invoking Space before a numbered row")
    destination = command.add_mutually_exclusive_group()
    destination.add_argument("--before", type=int, metavar="NUMBER")
    destination.add_argument("--before-id", type=nonempty, metavar="ID")
    destination.add_argument("--to-end", action="store_true")
    command.add_argument("--json", action="store_true")
    command.add_argument("--quiet", action="store_true")
    return root


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args, client, source = None, None, None
    try:
        args = parser().parse_args(argv)
        source = args.source_workspace
        if args.source_tab is not None and args.resource != "tab":
            raise PlacementError("--source-tab requires the tab subcommand", stage="usage")
        interactive = args.resource == "reorder" and not (
            args.before is not None or args.before_id is not None or args.to_end
        )
        if interactive and (args.json or not sys.stdin.isatty() or not sys.stdout.isatty()):
            raise PlacementError(
                "reorder needs a terminal or a destination option", stage="context"
            )
        context = dict(os.environ)
        socket_path = args.socket or context.get("HERDR_SOCKET_PATH")
        source = args.source_workspace or context.get("HERDR_ACTIVE_WORKSPACE_ID")
        if source is None and not context.get("HERDR_PANE_ID"):
            source = context.get("HERDR_WORKSPACE_ID")
        if socket_path and (args.socket is None or args.source_workspace):
            client = Client(socket_path)
        if args.resource == "tab":
            source = args.source_tab or context.get("HERDR_ACTIVE_TAB_ID")
            client, workspace, source = capture_tab(
                args.socket, args.source_workspace, args.source_tab, context, client=client
            )
            outcome = create_tab_after(
                client, workspace, source, label=args.label, cwd=args.cwd, focus=not args.no_focus
            )
        else:
            client, source = capture(args.socket, args.source_workspace, context, client=client)
        if args.resource == "workspace":
            outcome = create_after(
                client, source, label=args.label, cwd=args.cwd, focus=not args.no_focus
            )
        elif args.resource == "tab":
            pass
        elif interactive:
            from .tui import run

            outcome = run(client, source, lambda failure: report_failure(client, failure))
        else:
            outcome = move_before(client, source, before=args.before_id, number=args.before)
    except (PlacementError, ClientError, OSError) as error:
        outcome = Outcome(
            (
                "uncertain"
                if getattr(error, "code", 2) == 4
                else "incomplete"
                if getattr(error, "code", 2) == 3
                else "error"
            ),
            source,
            getattr(error, "new_id", None),
            getattr(error, "stage", "context"),
            str(error),
            getattr(error, "code", 2),
        )
    except KeyboardInterrupt:
        # An interrupt could arrive after a mutation was sent. Never claim a safe cancel.
        outcome = Outcome("uncertain", source, stage="interrupted", error="interrupted", code=4)
    resource = "tab" if getattr(args, "resource", None) == "tab" else "Space"
    if outcome.code:
        report_failure(client, outcome, resource)
    if "--json" in argv:
        print(json.dumps(asdict(outcome)))
    elif outcome.code:
        detail = f"; preserved new {resource} {outcome.new_id}" if outcome.new_id else ""
        print(
            f"herdr-next-to-current: {outcome.error}{detail} (stage: {outcome.stage})",
            file=sys.stderr,
        )
    elif not getattr(args, "quiet", False):
        print(f"{outcome.status}: {outcome.new_id or outcome.source_id} ({outcome.stage})")
    return outcome.code
