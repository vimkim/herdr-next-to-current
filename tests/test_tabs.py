import concurrent.futures
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from herdr_next_to_current.cli import main
from herdr_next_to_current.client import Client
from herdr_next_to_current.placement import PlacementError, mutation_lock
from herdr_next_to_current.tabs import capture_tab, create_tab_after
from tests.fake_herdr import DROP, FakeHerdr, tab


class Tabs(unittest.TestCase):
    def setUp(self):
        self.server = FakeHerdr()
        self.addCleanup(self.server.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.server.tabs["b"] = [tab(t, focused=t == "B") for t in ("A", "B", "C")]
        self.client = Client(self.server.path)

    def cli(self, *args, env=None):
        clean = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
        clean.update(XDG_STATE_HOME=self.tmp.name)
        clean.update(env or {})
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.dict(os.environ, clean, clear=True),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def invoke(self, *args, source="B"):
        return self.cli(
            "tab",
            *args,
            env={
                "HERDR_SOCKET_PATH": self.server.path,
                "HERDR_ACTIVE_WORKSPACE_ID": "b",
                "HERDR_ACTIVE_TAB_ID": source,
            },
        )

    def listed(self, workspace="b"):
        return self.client.call("tab.list", {"workspace_id": workspace}, "tab_list")["tabs"]

    def test_middle_source_creates_adjacent_focused_tab(self):
        code, output, error = self.invoke("--json")
        self.assertEqual(code, 0, error + output)
        result = json.loads(output)
        self.assertEqual((result["source_id"], result["stage"]), ("B", "focused"))
        self.assertEqual([t["tab_id"] for t in self.listed()], ["A", "B", result["new_id"], "C"])
        self.assertEqual([t["tab_id"] for t in self.listed() if t["focused"]], [result["new_id"]])

    def test_explicit_tab_and_workspace_override_inherited_context(self):
        code, output, error = self.cli(
            "--socket",
            self.server.path,
            "--source-workspace",
            "b",
            "--source-tab",
            "B",
            "tab",
            "--json",
            env={
                "HERDR_SOCKET_PATH": "/bad/socket",
                "HERDR_ACTIVE_WORKSPACE_ID": "stale",
                "HERDR_ACTIVE_TAB_ID": "stale",
                "HERDR_PANE_ID": "stale",
            },
        )
        self.assertEqual(code, 0, output + error)
        self.assertEqual(json.loads(output)["source_id"], "B")

    def test_pane_invocation_resolves_live_tab_and_workspace_once(self):
        self.server.pane_workspace, self.server.pane_tab = "c", "c:t1"
        code, output, error = self.cli(
            "tab",
            "--json",
            env={
                "HERDR_SOCKET_PATH": self.server.path,
                "HERDR_PANE_ID": "old:pane",
                "HERDR_WORKSPACE_ID": "stale",
                "HERDR_TAB_ID": "stale",
            },
        )
        self.assertEqual(code, 0, output + error)
        result = json.loads(output)
        self.assertEqual(result["source_id"], "c:t1")
        self.assertEqual([t["tab_id"] for t in self.listed("c")], ["c:t1", result["new_id"]])
        self.assertEqual(sum(r["method"] == "pane.current" for r in self.server.requests), 1)

    def test_lost_move_and_focus_responses_reconcile_without_retry(self):
        for method in ("tab.move", "tab.focus"):
            with self.subTest(method=method):
                self.server.hooks.clear()
                self.server.requests.clear()

                def lost(params, method=method):
                    self.server.dispatch(method, params)
                    return DROP

                self.server.hooks[method] = lost
                code, output, error = self.invoke("--json")
                self.assertEqual(code, 0, output + error)
                result = json.loads(output)
                self.assertEqual(
                    [t["tab_id"] for t in self.listed() if t["focused"]], [result["new_id"]]
                )
                self.assertEqual(sum(r["method"] == method for r in self.server.mutations), 1)

    def test_final_and_only_tab_skip_movement_and_preserve_focus(self):
        for ids in (("A", "B"), ("B",)):
            with self.subTest(ids=ids):
                self.server.tabs["b"] = [tab(t, focused=t == "B") for t in ids]
                self.server.requests.clear()
                code, output, error = self.invoke("--no-focus", "--json")
                self.assertEqual(code, 0, output + error)
                result = json.loads(output)
                self.assertEqual([t["tab_id"] for t in self.listed()], [*ids, result["new_id"]])
                self.assertEqual(result["stage"], "placed")
                self.assertEqual([t["tab_id"] for t in self.listed() if t["focused"]], ["B"])
                self.assertEqual([r["method"] for r in self.server.mutations], ["tab.create"])

    def test_label_absolute_cwd_and_quiet_options(self):
        code, output, error = self.invoke("--label", "review", "--cwd", "./project", "--quiet")
        self.assertEqual((code, output, error), (0, "", ""))
        self.assertEqual(
            self.server.mutations[0]["params"],
            {
                "workspace_id": "b",
                "focus": False,
                "label": "review",
                "cwd": str(Path("project").resolve()),
            },
        )
        self.assertEqual(self.listed()[2]["label"], "review")

    def test_custom_context_ignores_stale_inherited_pane_and_uses_ids_after_rename(self):
        def create(params):
            self.server.tabs["b"][1]["label"] = "renamed"
            return self.server.dispatch("tab.create", params)

        self.server.hooks["tab.create"] = create
        code, output, error = self.cli(
            "tab",
            "--json",
            env={
                "HERDR_SOCKET_PATH": self.server.path,
                "HERDR_ACTIVE_WORKSPACE_ID": "b",
                "HERDR_ACTIVE_TAB_ID": "B",
                "HERDR_PANE_ID": "stale",
                "HERDR_WORKSPACE_ID": "stale",
                "HERDR_TAB_ID": "stale",
            },
        )
        self.assertEqual(code, 0, output + error)
        self.assertEqual(
            [t["tab_id"] for t in self.listed()], ["A", "B", json.loads(output)["new_id"], "C"]
        )
        self.assertNotIn("pane.current", [r["method"] for r in self.server.requests])
        self.assertNotIn("cwd", self.server.mutations[0]["params"])

    def test_missing_stale_or_conflicting_context_never_creates(self):
        for context in (
            {},
            {"HERDR_ACTIVE_WORKSPACE_ID": "b"},
            {"HERDR_ACTIVE_TAB_ID": "B"},
            {"HERDR_ACTIVE_WORKSPACE_ID": "b", "HERDR_ACTIVE_TAB_ID": "c:t1"},
            {"HERDR_ACTIVE_WORKSPACE_ID": "b", "HERDR_ACTIVE_TAB_ID": "missing"},
            {"HERDR_WORKSPACE_ID": "b"},
        ):
            with self.subTest(context=context):
                code, _, _ = self.cli("tab", env={"HERDR_SOCKET_PATH": self.server.path, **context})
                self.assertEqual(code, 2)
        for selectors in (
            ("--socket", self.server.path),
            ("--source-workspace", "b"),
            ("--source-tab", "B"),
        ):
            code, _, _ = self.cli(
                *selectors,
                "tab",
                env={
                    "HERDR_SOCKET_PATH": self.server.path,
                    "HERDR_ACTIVE_WORKSPACE_ID": "b",
                    "HERDR_ACTIVE_TAB_ID": "B",
                },
            )
            self.assertEqual(code, 2)
        self.assertFalse(self.server.mutations)

    def test_stale_pane_never_falls_back_to_workspace_or_global_focus(self):
        self.server.pane_workspace = None
        code, output, _ = self.cli(
            "tab",
            "--json",
            env={
                "HERDR_SOCKET_PATH": self.server.path,
                "HERDR_PANE_ID": "stale",
                "HERDR_WORKSPACE_ID": "b",
                "HERDR_TAB_ID": "B",
            },
        )
        self.assertEqual(code, 2, output)
        self.assertFalse(self.server.mutations)

    def test_workspace_and_tab_environment_without_pane_is_validated(self):
        code, output, error = self.cli(
            "tab",
            "--json",
            env={
                "HERDR_SOCKET_PATH": self.server.path,
                "HERDR_WORKSPACE_ID": "b",
                "HERDR_TAB_ID": "B",
            },
        )
        self.assertEqual(code, 0, output + error)
        self.assertEqual(json.loads(output)["source_id"], "B")

    def test_unsupported_server_never_creates(self):
        for version, protocol in (("0.9.4", 22), ("0.9.3", 23)):
            self.server.version, self.server.protocol = version, protocol
            self.assertEqual(self.invoke()[0], 2)
        self.assertFalse(self.server.mutations)

    def test_definitive_create_move_and_focus_failures_preserve_known_tab(self):
        for method, code, stage in (
            ("tab.create", 2, "validated"),
            ("tab.move", 3, "created"),
            ("tab.focus", 3, "placed"),
        ):
            with self.subTest(method=method):
                self.server.hooks.clear()
                self.server.hooks[method] = lambda p: {
                    "code": "denied",
                    "message": "test rejection",
                }
                actual, output, _ = self.invoke("--json")
                result = json.loads(output)
                self.assertEqual((actual, result["stage"]), (code, stage))
                if method == "tab.create":
                    self.assertIsNone(result["new_id"])
                else:
                    self.assertIn(result["new_id"], [t["tab_id"] for t in self.listed()])

    def test_lost_create_never_retries_or_infers_new_identity(self):
        def lost(params):
            self.server.dispatch("tab.create", params)
            return DROP

        self.server.hooks["tab.create"] = lost
        code, output, _ = self.invoke("--json")
        self.assertEqual(code, 4)
        self.assertIsNone(json.loads(output)["new_id"])
        self.assertEqual(len(self.listed()), 4)
        self.assertEqual([r["method"] for r in self.server.mutations], ["tab.create"])

    def test_unapplied_lost_move_and_focus_remain_uncertain(self):
        for method in ("tab.move", "tab.focus"):
            self.server.hooks.clear()
            self.server.requests.clear()
            self.server.hooks[method] = lambda p: DROP
            code, output, _ = self.invoke("--json")
            self.assertEqual(code, 4)
            self.assertIn(json.loads(output)["new_id"], [t["tab_id"] for t in self.listed()])
            self.assertEqual(sum(r["method"] == method for r in self.server.mutations), 1)

    def test_source_removed_after_create_preserves_tab_without_moving(self):
        def create(params):
            result = self.server.dispatch("tab.create", params)
            self.server.tabs["b"] = [t for t in self.server.tabs["b"] if t["tab_id"] != "B"]
            return result

        self.server.hooks["tab.create"] = create
        code, output, error = self.invoke()
        self.assertEqual(code, 3, output + error)
        self.assertIn("preserved new tab", error)
        self.assertEqual(len(self.listed()), 3)
        self.assertEqual([r["method"] for r in self.server.mutations], ["tab.create"])

    def test_concurrent_reorder_is_reported_without_repeated_moves(self):
        def move(params):
            result = self.server.dispatch("tab.move", params)
            self.server.tabs["b"].reverse()
            return result

        self.server.hooks["tab.move"] = move
        code, output, _ = self.invoke("--json")
        self.assertEqual(code, 4)
        self.assertIn(json.loads(output)["new_id"], [t["tab_id"] for t in self.listed()])
        self.assertEqual([r["method"] for r in self.server.mutations], ["tab.create", "tab.move"])

    def test_fresh_order_handles_created_tab_moved_to_start_before_placement(self):
        def create(params):
            result = self.server.dispatch("tab.create", params)
            self.server.tabs["b"].insert(0, self.server.tabs["b"].pop())
            return result

        self.server.hooks["tab.create"] = create
        code, output, error = self.invoke("--json")
        self.assertEqual(code, 0, output + error)
        self.assertEqual(
            [t["tab_id"] for t in self.listed()], ["A", "B", json.loads(output)["new_id"], "C"]
        )

    def test_created_tab_response_never_reuses_or_infers_identity(self):
        for response in ({}, {"tab_id": ""}, {"tab_id": "B"}):
            with self.subTest(response=response):
                self.server.requests.clear()
                self.server.hooks["tab.create"] = lambda p, response=response: {
                    "type": "tab_created",
                    "tab": response,
                }
                code, output, _ = self.invoke("--json")
                self.assertEqual(code, 4)
                self.assertIsNone(json.loads(output)["new_id"])
                self.assertEqual([r["method"] for r in self.server.mutations], ["tab.create"])

    def test_malformed_move_or_focus_result_preserves_tab_and_reports_uncertainty(self):
        for method, result in (
            ("tab.move", {"type": "tab_list", "tabs": []}),
            ("tab.move", {"type": "tab_list", "tabs": [{}]}),
            ("tab.focus", {"type": "tab_info", "tab": {}}),
        ):
            with self.subTest(method=method, result=result):
                self.server.hooks.clear()
                self.server.hooks[method] = lambda p, result=result: result
                code, output, _ = self.invoke("--json")
                self.assertEqual(code, 4)
                self.assertIn(json.loads(output)["new_id"], [t["tab_id"] for t in self.listed()])

    def test_failed_reconciliation_does_not_hide_uncertain_mutation(self):
        for method in ("tab.move", "tab.focus"):
            self.server.hooks.clear()

            def lost(params, method=method):
                self.server.dispatch(method, params)
                self.server.hooks["tab.list"] = lambda p: {
                    "code": "unavailable",
                    "message": "read failed",
                }
                return DROP

            self.server.hooks[method] = lost
            code, output, _ = self.invoke("--json")
            self.assertEqual(code, 4)
            self.assertIsNotNone(json.loads(output)["new_id"])

    def test_membership_changed_after_create_keeps_known_tab(self):
        def create(params):
            result = self.server.dispatch("tab.create", params)
            self.server.tabs["b"][-1]["workspace_id"] = "c"
            return result

        self.server.hooks["tab.create"] = create
        code, output, _ = self.invoke("--json")
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(output)["new_id"], "new-tab-1")
        self.assertEqual([r["method"] for r in self.server.mutations], ["tab.create"])

    def test_stale_captured_source_is_revalidated_before_creation(self):
        client, workspace, source = capture_tab(self.server.path, "b", "B", {}, client=self.client)
        self.server.tabs["b"].pop(1)
        with (
            patch.dict(os.environ, {"XDG_STATE_HOME": self.tmp.name}),
            self.assertRaises(PlacementError) as caught,
        ):
            create_tab_after(client, workspace, source)
        self.assertEqual(caught.exception.code, 2)
        self.assertFalse(self.server.mutations)

    def test_tab_creations_serialize_and_share_workspace_mutation_lock(self):
        with patch.dict(os.environ, {"XDG_STATE_HOME": self.tmp.name}):
            with mutation_lock(self.client), self.assertRaises(PlacementError):
                with mutation_lock(self.client, timeout=0.03):
                    self.fail("lock acquired twice")
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                results = list(
                    pool.map(
                        lambda _: create_tab_after(self.client, "b", "B", focus=False), range(2)
                    )
                )
        rows = [t["tab_id"] for t in self.listed()]
        self.assertEqual(rows[:2], ["A", "B"])
        self.assertEqual(rows[-1], "C")
        self.assertEqual(set(rows[2:4]), {r.new_id for r in results})
        self.assertEqual(
            [r["method"] for r in self.server.mutations], ["tab.create", "tab.move"] * 2
        )

    def test_failure_notification_and_log_identify_tab(self):
        self.server.hooks["tab.move"] = lambda p: {"code": "denied", "message": "test rejection"}
        code, _, error = self.invoke()
        self.assertEqual(code, 3)
        self.assertIn("preserved new tab", error)
        notification = next(r for r in self.server.requests if r["method"] == "notification.show")
        self.assertEqual(notification["params"]["title"], "tab operation failed")
        log = Path(self.tmp.name) / "herdr-next-to-current/failures.log"
        self.assertEqual(json.loads(log.read_text())["new_id"], "new-tab-1")

    def test_process_interrupt_preserves_created_identity_when_known(self):
        for method, stage in (
            ("tab.create", "validated"),
            ("tab.move", "created"),
            ("tab.focus", "placed"),
        ):
            with self.subTest(method=method):
                self.server.hooks.clear()
                entered, release = threading.Event(), threading.Event()

                def blocked(params, method=method, entered=entered, release=release):
                    self.server.dispatch(method, params)
                    entered.set()
                    release.wait(timeout=5)
                    return DROP

                self.server.hooks[method] = blocked
                env = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
                env["XDG_STATE_HOME"] = self.tmp.name
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        "from herdr_next_to_current.cli import main; raise SystemExit(main())",
                        "--socket",
                        self.server.path,
                        "--source-workspace",
                        "b",
                        "--source-tab",
                        "B",
                        "tab",
                        "--json",
                    ],
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                try:
                    self.assertTrue(entered.wait(timeout=5), "CLI did not send mutation")
                    process.send_signal(signal.SIGINT)
                    release.set()
                    output, error = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 4, output + error)
                    result = json.loads(output)
                    self.assertEqual((result["stage"], result["error"]), (stage, "interrupted"))
                    if method == "tab.create":
                        self.assertIsNone(result["new_id"])
                    else:
                        self.assertIn(result["new_id"], [t["tab_id"] for t in self.listed()])
                finally:
                    release.set()
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)

    def test_tab_env_forwarding_and_validation(self):
        code, output, error = self.invoke(
            "--env",
            "HERDR_SHELL=bash",
            "--env",
            "HERDR_SHELL=nu",
            "--env",
            "FOO=a=b",
            "--no-focus",
            "--json",
        )
        self.assertEqual(code, 0, output + error)
        self.assertEqual(
            self.server.mutations[0]["params"]["env"],
            {"HERDR_SHELL": "nu", "FOO": "a=b"},
        )

        self.server.requests.clear()
        for invalid in ("NO_EQUALS", "=value"):
            with self.subTest(invalid=invalid):
                code, output, _ = self.invoke("--env", invalid, "--json")
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(output)["stage"], "usage")
                self.assertFalse(self.server.requests)

        code, output, error = self.invoke("--no-focus", "--json")
        self.assertEqual(code, 0, output + error)
        self.assertNotIn("env", self.server.mutations[-1]["params"])
