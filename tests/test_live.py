"""Opt-in real Herdr verification, confined to disposable config/state/sockets.

Run: HERDR_LIVE_TEST=1 uv run python -m unittest tests.test_live -v
"""

import contextlib
import fcntl
import json
import os
import pty
import select
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from herdr_next_to_current.client import Client, ClientError
from herdr_next_to_current.placement import capture, create_after, move_before, read_state
from herdr_next_to_current.tabs import capture_tab, create_tab_after, read_tabs


@unittest.skipUnless(
    os.environ.get("HERDR_LIVE_TEST") == "1" and shutil.which("herdr"),
    "set HERDR_LIVE_TEST=1 to use a disposable Herdr 0.9.3 server",
)
class Live(unittest.TestCase):
    def test_isolated_server_and_two_terminal_clients(self):
        with tempfile.TemporaryDirectory(prefix="hntc-live-") as temporary:
            root = Path(temporary)
            env = {key: value for key, value in os.environ.items() if not key.startswith("HERDR_")}
            env.update(
                XDG_CONFIG_HOME=str(root / "config"),
                XDG_STATE_HOME=str(root / "state"),
                XDG_CACHE_HOME=str(root / "cache"),
                HERDR_CONFIG_PATH=str(root / "config.toml"),
                HERDR_SOCKET_PATH=str(root / "api.sock"),
                HERDR_SESSION="hntc-verification",
                TERM="xterm-256color",
            )
            env.pop("DISPLAY", None)
            config = (
                'onboarding = false\n[terminal]\ndefault_shell = "/bin/sh"\nnew_cwd = "follow"\n'
            )
            helper = root / "shortcut.py"
            helper.write_text(
                "import json, os\nfrom pathlib import Path\n"
                f"Path({str(root / 'popup-context.json')!r}).write_text("
                "json.dumps({k:v for k,v in os.environ.items() if k in "
                "('HERDR_ACTIVE_WORKSPACE_ID','HERDR_ACTIVE_TAB_ID',"
                "'HERDR_SOCKET_PATH','HERDR_PANE_ID')}))\n"
                "from herdr_next_to_current.cli import main\nraise SystemExit(main())\n"
            )
            command = shlex.join([sys.executable, str(helper)])
            config += (
                "[keys]\nnew_workspace = []\nnew_tab = []\n"
                '[[keys.command]]\nkey = "alt+t"\ntype = "shell"\n'
                f"command = {json.dumps(command + ' tab --quiet')}\n"
                '[[keys.command]]\nkey = "alt+c"\ntype = "shell"\n'
                f"command = {json.dumps(command + ' workspace --quiet')}\n"
                '[[keys.command]]\nkey = "alt+shift+c"\ntype = "popup"\n'
                f"command = {json.dumps(command + ' reorder --quiet')}\n"
                'width = "80%"\nheight = "80%"\n'
            )
            (root / "config.toml").write_text(config)
            log = (root / "server.log").open("w+")
            self.addCleanup(log.close)
            server = subprocess.Popen(["herdr", "server"], env=env, stdout=log, stderr=log)
            clients, terminals = [], []
            client = Client(str(root / "api.sock"), timeout=1)
            try:
                deadline = time.monotonic() + 8
                while True:
                    try:
                        client.validate()
                        break
                    except ClientError:
                        if server.poll() is not None or time.monotonic() > deadline:
                            log.seek(0)
                            self.fail(log.read())
                        time.sleep(0.03)
                for name in ("source", "other"):
                    (root / name).mkdir()
                source = client.call(
                    "workspace.create",
                    {"cwd": str(root / "source"), "focus": True},
                    "workspace_created",
                    mutation=True,
                )
                source_id = source["workspace"]["workspace_id"]
                other = client.call(
                    "workspace.create",
                    {"cwd": str(root / "other"), "focus": True},
                    "workspace_created",
                    mutation=True,
                )["workspace"]["workspace_id"]
                for _ in range(2):
                    master, slave = pty.openpty()
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 120, 0, 0))
                    terminals.extend((master, slave))
                    clients.append(
                        subprocess.Popen(
                            ["herdr", "client"], env=env, stdin=slave, stdout=slave, stderr=slave
                        )
                    )
                # Drain startup frames without waiting on a GUI or changing working sessions.
                deadline = time.monotonic() + 0.5
                frames = b""
                while time.monotonic() < deadline:
                    for fd in select.select(terminals[::2], [], [], 0.05)[0]:
                        frames += os.read(fd, 65536)
                self.assertTrue(
                    all(process.poll() is None for process in clients),
                    frames.decode(errors="replace"),
                )
                with patch.dict(os.environ, {"XDG_STATE_HOME": str(root / "state")}):
                    created = create_after(client, source_id, focus=False)
                    self.assertEqual(read_state(client).ids, [source_id, created.new_id, other])
                    self.assertTrue(
                        next(r for r in read_state(client).raw if r["workspace_id"] == other)[
                            "focused"
                        ]
                    )
                    snapshot = client.call("session.snapshot", {}, "session_snapshot")["snapshot"]
                    new_pane = next(
                        p for p in snapshot["panes"] if p["workspace_id"] == created.new_id
                    )
                    self.assertEqual(new_pane["cwd"], str(root / "source"))
                    pane_id = source["root_pane"]["pane_id"]
                    _, canonical = capture(
                        None, None, {"HERDR_SOCKET_PATH": client.path, "HERDR_PANE_ID": pane_id}
                    )
                    self.assertEqual(canonical, source_id)
                    before = client.call(
                        "pane.process_info", {"pane_id": pane_id}, "pane_process_info"
                    )
                    move_before(client, source_id, before=other)
                    after = client.call(
                        "pane.process_info", {"pane_id": pane_id}, "pane_process_info"
                    )
                    self.assertEqual(
                        before["process_info"]["shell_pid"], after["process_info"]["shell_pid"]
                    )
                    self.assertTrue(
                        next(r for r in read_state(client).raw if r["workspace_id"] == other)[
                            "focused"
                        ]
                    )
                    focused = create_after(client, source_id)
                    self.assertTrue(
                        next(
                            r for r in read_state(client).raw if r["workspace_id"] == focused.new_id
                        )["focused"]
                    )
                    final = client.call("session.snapshot", {}, "session_snapshot")["snapshot"]

                    def identities(snapshot):
                        return {
                            p["pane_id"]: (p["terminal_id"], p["workspace_id"], p["tab_id"])
                            for p in snapshot["panes"]
                        }

                    self.assertTrue(identities(snapshot).items() <= identities(final).items())

                    # Real tab creation: middle, final, and only-tab sources, both focus modes.
                    tab_a = source["tab"]["tab_id"]
                    tab_b, tab_c = [
                        client.call(
                            "tab.create",
                            {"workspace_id": source_id, "focus": False},
                            "tab_created",
                            mutation=True,
                        )["tab"]["tab_id"]
                        for _ in range(2)
                    ]
                    before_tabs = client.call("session.snapshot", {}, "session_snapshot")[
                        "snapshot"
                    ]
                    processes = {
                        p["pane_id"]: client.call(
                            "pane.process_info", {"pane_id": p["pane_id"]}, "pane_process_info"
                        )["process_info"]["shell_pid"]
                        for p in before_tabs["panes"]
                    }
                    _, pane_workspace, pane_tab = capture_tab(
                        None,
                        None,
                        None,
                        {"HERDR_SOCKET_PATH": client.path, "HERDR_PANE_ID": pane_id},
                    )
                    self.assertEqual((pane_workspace, pane_tab), (source_id, tab_a))
                    middle = create_tab_after(client, source_id, tab_b, label="review")
                    self.assertEqual(
                        read_tabs(client, source_id).ids, [tab_a, tab_b, middle.new_id, tab_c]
                    )
                    self.assertTrue(
                        next(
                            t
                            for t in read_tabs(client, source_id).rows
                            if t["tab_id"] == middle.new_id
                        )["focused"]
                    )
                    last = create_tab_after(client, source_id, tab_c, focus=False)
                    self.assertEqual(read_tabs(client, source_id).ids[-2:], [tab_c, last.new_id])
                    other_tab = read_tabs(client, other).ids[0]
                    only = create_tab_after(client, other, other_tab, focus=False)
                    self.assertEqual(read_tabs(client, other).ids, [other_tab, only.new_id])
                    self.assertTrue(
                        next(
                            t
                            for t in read_tabs(client, source_id).rows
                            if t["tab_id"] == middle.new_id
                        )["focused"]
                    )
                    after_tabs = client.call("session.snapshot", {}, "session_snapshot")["snapshot"]
                    self.assertTrue(
                        identities(before_tabs).items() <= identities(after_tabs).items()
                    )
                    for old_pane, pid in processes.items():
                        self.assertEqual(
                            client.call(
                                "pane.process_info", {"pane_id": old_pane}, "pane_process_info"
                            )["process_info"]["shell_pid"],
                            pid,
                        )
                    middle_pane = next(
                        p for p in after_tabs["panes"] if p["tab_id"] == middle.new_id
                    )
                    self.assertEqual(middle_pane["cwd"], str(root / "source"))
                    self.assertEqual(
                        next(
                            t
                            for t in read_tabs(client, source_id).rows
                            if t["tab_id"] == middle.new_id
                        )["label"],
                        "review",
                    )

                def wait_until(predicate, label):
                    deadline = time.monotonic() + 5
                    output = b""
                    while time.monotonic() < deadline:
                        for fd in select.select(terminals[::2], [], [], 0.03)[0]:
                            output += os.read(fd, 65536)
                        if predicate(output):
                            return output
                    self.fail(f"{label}: {output.decode(errors='replace')}")

                before_ids = read_state(client).ids
                os.write(terminals[0], b"\x1bc")
                wait_until(
                    lambda _: len(read_state(client).ids) == len(before_ids) + 1,
                    "Alt+C creates through the real shell binding",
                )
                new_id = next(item for item in read_state(client).ids if item not in before_ids)
                wait_until(
                    lambda _: next(
                        r for r in read_state(client).raw if r["workspace_id"] == new_id
                    )["focused"],
                    "shortcut focuses the new Space",
                )
                captured = json.loads((root / "popup-context.json").read_text())
                invoking_id = captured["HERDR_ACTIVE_WORKSPACE_ID"]

                def adjacent(_):
                    rows = read_state(client).ids
                    return rows.index(new_id) == rows.index(invoking_id) + 1

                wait_until(adjacent, "shortcut places below its invoking client Space")

                shortcut_a = read_tabs(client, new_id).ids[0]
                shortcut_b, shortcut_c = [
                    client.call(
                        "tab.create",
                        {"workspace_id": new_id, "focus": False},
                        "tab_created",
                        mutation=True,
                    )["tab"]["tab_id"]
                    for _ in range(2)
                ]
                client.call("tab.focus", {"tab_id": shortcut_b}, "tab_info", mutation=True)
                # Give both PTY clients time to receive the public focus projection.
                deadline = time.monotonic() + 0.3
                while time.monotonic() < deadline:
                    for fd in select.select(terminals[::2], [], [], 0.03)[0]:
                        os.read(fd, 65536)
                shortcut_ids = read_tabs(client, new_id).ids
                os.write(terminals[0], b"\x1bt")
                wait_until(
                    lambda _: len(read_tabs(client, new_id).ids) == 4,
                    "Alt+T creates through the real shell binding",
                )
                shortcut_new = next(
                    t for t in read_tabs(client, new_id).ids if t not in shortcut_ids
                )
                wait_until(
                    lambda _: any(
                        t["tab_id"] == shortcut_new and t["focused"]
                        for t in read_tabs(client, new_id).rows
                    ),
                    "Alt+T focuses the new tab",
                )
                self.assertEqual(
                    read_tabs(client, new_id).ids,
                    [shortcut_a, shortcut_b, shortcut_new, shortcut_c],
                )
                tab_context = json.loads((root / "popup-context.json").read_text())
                self.assertEqual(tab_context["HERDR_ACTIVE_TAB_ID"], shortcut_b)
                self.assertEqual(tab_context["HERDR_ACTIVE_WORKSPACE_ID"], new_id)
                os.write(terminals[0], b"\x1bC")
                wait_until(
                    lambda output: b"Insert current Space before number" in output,
                    "Alt+Shift+C opens the numeric popup",
                )
                popup_context = json.loads((root / "popup-context.json").read_text())
                popup_source = popup_context["HERDR_ACTIVE_WORKSPACE_ID"]
                self.assertIn(popup_source, read_state(client).ids)
                self.assertEqual(popup_context["HERDR_SOCKET_PATH"], client.path)
                focused_before_popup_move = next(
                    r["workspace_id"] for r in read_state(client).raw if r["focused"]
                )
                os.write(terminals[0], b"1\n")
                wait_until(
                    lambda _: read_state(client).ids[0] == popup_source,
                    "popup moves its captured Space before row one",
                )
                self.assertTrue(
                    next(
                        r
                        for r in read_state(client).raw
                        if r["workspace_id"] == focused_before_popup_move
                    )["focused"]
                )
                # Omitting cwd must honor server policy; explicit cwd must override it.
                (root / "policy").mkdir()
                (root / "explicit").mkdir()
                (root / "config.toml").write_text(
                    config.replace(
                        'new_cwd = "follow"', f"new_cwd = {json.dumps(str(root / 'policy'))}"
                    )
                )
                client.call("server.reload_config", {}, "config_reload", mutation=True)
                with patch.dict(os.environ, {"XDG_STATE_HOME": str(root / "state")}):
                    policy_created = create_after(client, popup_source, focus=False)
                    explicit_created = create_after(
                        client, popup_source, cwd=str(root / "explicit"), focus=False
                    )
                    policy_tab = create_tab_after(client, source_id, tab_b, focus=False)
                    explicit_tab = create_tab_after(
                        client, source_id, tab_b, cwd=str(root / "explicit"), focus=False
                    )
                panes = client.call("session.snapshot", {}, "session_snapshot")["snapshot"]["panes"]
                self.assertEqual(
                    next(p for p in panes if p["workspace_id"] == policy_created.new_id)["cwd"],
                    str(root / "policy"),
                )
                self.assertEqual(
                    next(p for p in panes if p["workspace_id"] == explicit_created.new_id)["cwd"],
                    str(root / "explicit"),
                )
                self.assertEqual(
                    next(p for p in panes if p["tab_id"] == policy_tab.new_id)["cwd"],
                    str(root / "policy"),
                )
                self.assertEqual(
                    next(p for p in panes if p["tab_id"] == explicit_tab.new_id)["cwd"],
                    str(root / "explicit"),
                )
                print(
                    "Verified Herdr 0.9.3: two clients, source cwd, adjacency, focus, "
                    "tab creation/placement/policy/focus, reorder, pane/process identities, "
                    "Alt+T, Alt+C and Alt+Shift+C popup context"
                )
            finally:
                for process in clients:
                    process.terminate()
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        process.wait(timeout=2)
                    if process.poll() is None:
                        process.kill()
                        process.wait()
                for fd in terminals:
                    os.close(fd)
                if server.poll() is None:
                    with contextlib.suppress(ClientError):
                        client.call("server.stop", {}, "ok", mutation=True)
                    with contextlib.suppress(subprocess.TimeoutExpired):
                        server.wait(timeout=3)
                if server.poll() is None:
                    server.terminate()
                    server.wait(timeout=3)
