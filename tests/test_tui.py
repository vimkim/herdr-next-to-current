import contextlib
import curses
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from unittest.mock import patch

from herdr_next_to_current.client import Client
from herdr_next_to_current.tui import picker
from tests.fake_herdr import DROP, FakeHerdr, row


class Screen:
    def __init__(self, keys):
        self.keys = iter(keys)
        self.rendered = []

    def keypad(self, flag):
        pass

    def getmaxyx(self):
        return 12, 90

    def erase(self):
        pass

    def addnstr(self, y, x, text, width):
        self.rendered.append(text)

    def refresh(self):
        pass

    def get_wch(self):
        key = next(self.keys)
        return key() if callable(key) else key


class Picker(unittest.TestCase):
    def setUp(self):
        self.server = FakeHerdr()
        self.addCleanup(self.server.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        env = patch.dict(os.environ, {"XDG_STATE_HOME": self.tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.client = Client(self.server.path)

    def test_multiple_digits_backspace_resize_and_scrolling(self):
        self.server.rows = [row(str(i)) for i in range(15)]
        screen = Screen(
            [
                curses.KEY_NPAGE,
                curses.KEY_RESIZE,
                curses.KEY_PPAGE,
                "1",
                "9",
                curses.KEY_BACKSPACE,
                "2",
                "\n",
            ]
        )
        outcome = picker(screen, self.client, "0")
        self.assertEqual(outcome.code, 0)
        self.assertEqual(self.server.ids.index("0"), 10)
        self.assertTrue(any("end of list" in text for text in screen.rendered) is False)

    def test_empty_zero_out_of_range_then_cancel(self):
        screen = Screen(["\n", "0", "\n", curses.KEY_BACKSPACE, "9", "\n", "q"])
        self.assertEqual(picker(screen, self.client, "b").status, "cancelled")
        self.assertFalse(self.server.mutations)
        self.assertTrue(any("choose a number" in text for text in screen.rendered))

    def test_changes_while_typing_clear_mapping_before_new_selection(self):
        def changed():
            self.server.rows.reverse()
            return "\n"

        screen = Screen(["1", changed, "q"])
        self.assertEqual(picker(screen, self.client, "b").status, "cancelled")
        self.assertFalse(self.server.mutations)
        self.assertTrue(any("changed; choose" in text for text in screen.rendered))

    def test_failed_move_stays_visible(self):
        self.server.hooks["workspace.move_block"] = lambda p: {
            "code": "denied",
            "message": "retry later",
        }
        screen = Screen(["1", "\n", "q"])
        picker(screen, self.client, "b")
        self.assertTrue(any("retry later" in text for text in screen.rendered))
        self.assertEqual(len(self.server.mutations), 1)

    def test_refresh_updates_numbers_and_clears_input(self):
        def changed():
            self.server.rows.reverse()
            return "r"

        screen = Screen(["2", changed, "1", "\n"])
        picker(screen, self.client, "b")
        self.assertEqual(self.server.ids, ["b", "c", "a"])

    def test_negative_numbers_are_rejected(self):
        screen = Screen(["-", "1", "\n", "q"])
        self.assertEqual(picker(screen, self.client, "b").status, "cancelled")
        self.assertFalse(self.server.mutations)
        self.assertTrue(any("choose a number" in text for text in screen.rendered))

    def test_uncertain_move_is_logged_and_cancel_preserves_error(self):
        self.server.hooks["workspace.move_block"] = lambda p: DROP
        failures = []
        outcome = picker(Screen(["1", "\n", "q"]), self.client, "b", failures.append)
        self.assertEqual(outcome.code, 4)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].code, 4)
        self.assertEqual(len(self.server.mutations), 1)

    def test_grouped_destination_is_numbered_and_explained(self):
        self.server.rows = [
            row("root", key="repo"),
            row("a"),
            row("child", key="repo", linked=True),
        ]
        screen = Screen(["2", "\n", "q"])
        picker(screen, self.client, "a")
        self.assertTrue(
            any("2  duplicate label  [Git worktree group" in t for t in screen.rendered)
        )
        self.assertTrue(any("belongs to a Git worktree group" in t for t in screen.rendered))
        self.assertFalse(self.server.mutations)

    def test_real_pty_restores_terminal_on_success_cancel_and_error(self):
        for keys, expected in ((b"1\n", 0), (b"q", 0), (b"\x1b", 0)):
            with self.subTest(keys=keys):
                self.server.rows = [row(i) for i in ("a", "b", "c")]
                self.run_pty(keys, expected)
        self.server.hooks["workspace.move_block"] = lambda p: {
            "code": "denied",
            "message": "retry later",
        }
        self.run_pty(b"1\nq", 0)
        self.server.hooks.clear()
        self.server.rows = [row("b", key="repo"), row("child", key="repo", linked=True)]
        self.run_pty(b"", 2, wait_for_prompt=False)

    def run_pty(self, keys, expected, wait_for_prompt=True):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        self.addCleanup(os.close, slave)
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 14, 90, 0, 0))
        original = termios.tcgetattr(slave)
        env = dict(os.environ, TERM="xterm-256color")
        command = [
            sys.executable,
            "-c",
            "from herdr_next_to_current.cli import main; raise SystemExit(main())",
            "--socket",
            self.server.path,
            "--source-workspace",
            "b",
            "reorder",
            "--quiet",
        ]
        process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, env=env)
        try:
            output = b""
            deadline = time.monotonic() + 5
            while process.poll() is None and time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    output += os.read(master, 65536)
                if wait_for_prompt and b"Insert current Space" in output:
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 18, 80, 0, 0))
                    process.send_signal(signal.SIGWINCH)
                    os.write(master, keys)
                    wait_for_prompt = False
            self.assertEqual(process.wait(timeout=1), expected, output.decode(errors="replace"))
            self.assertEqual(termios.tcgetattr(slave), original)
        finally:
            if process.poll() is None:
                process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                process.wait(timeout=1)
