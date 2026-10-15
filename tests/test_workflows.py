import concurrent.futures
import contextlib
import io
import itertools
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from herdr_next_to_current.cli import failure_log, main
from herdr_next_to_current.client import Client, ClientError
from herdr_next_to_current.placement import (
    Changed,
    PlacementError,
    capture,
    create_after,
    move_before,
    mutation_lock,
    read_state,
)
from tests.fake_herdr import DROP, FakeHerdr, row


class Workflows(unittest.TestCase):
    def setUp(self):
        self.server = FakeHerdr()
        self.addCleanup(self.server.close)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {"XDG_STATE_HOME": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = Client(self.server.path, timeout=0.2)

    def cli(self, *args, env=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        clean = {k: v for k, v in os.environ.items() if not k.startswith("HERDR_")}
        clean.update(env or {})
        with (
            patch.dict(os.environ, clean, clear=True),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = main(list(args))
        return code, stdout.getvalue(), stderr.getvalue()

    def explicit(self, *args):
        return self.cli("--socket", self.server.path, "--source-workspace", "b", *args)

    def test_middle_create_and_focus_sequence(self):
        result = create_after(self.client, "b", label="review")
        self.assertEqual(self.server.ids, ["a", "b", result.new_id, "c"])
        self.assertEqual(
            [r["method"] for r in self.server.mutations],
            ["workspace.create", "workspace.move_block", "workspace.focus"],
        )
        params = self.server.mutations[0]["params"]
        self.assertEqual(params, {"source_workspace_id": "b", "focus": False, "label": "review"})
        self.assertTrue(
            next(r for r in self.server.rows if r["workspace_id"] == result.new_id)["focused"]
        )

    def test_end_and_only_workspace_skip_move(self):
        for ids in (["a", "b"], ["b"]):
            self.server.rows = [row(i) for i in ids]
            self.server.requests.clear()
            create_after(self.client, "b", focus=False)
            self.assertEqual([r["method"] for r in self.server.mutations], ["workspace.create"])

    def test_cwd_absolute_and_no_focus(self):
        code, output, _ = self.explicit("workspace", "--cwd", "./project", "--no-focus", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["stage"], "placed")
        self.assertEqual(self.server.mutations[0]["params"]["cwd"], str(Path("project").resolve()))
        self.assertTrue(self.server.rows[0]["focused"])

    def test_repeated_captured_source_creates_reverse_trigger_order(self):
        first = create_after(self.client, "b", focus=False)
        second = create_after(self.client, "b", focus=False)
        self.assertEqual(self.server.ids, ["a", "b", second.new_id, first.new_id, "c"])

    def test_concurrent_helpers_serialize(self):
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(
                pool.map(lambda _: create_after(self.client, "b", focus=False), range(2))
            )
        self.assertEqual(set(self.server.ids[2:4]), {r.new_id for r in results})
        self.assertEqual(
            [r["method"] for r in self.server.mutations],
            ["workspace.create", "workspace.move_block"] * 2,
        )

    def test_bounded_lock_wait(self):
        with mutation_lock(self.client), self.assertRaises(PlacementError):
            with mutation_lock(self.client, timeout=0.03):
                self.fail("lock acquired twice")
        self.assertFalse(self.server.mutations)

    def test_source_deleted_after_create_preserves_new_space(self):
        def create(params):
            result = self.server.dispatch("workspace.create", params)
            self.server.rows = [r for r in self.server.rows if r["workspace_id"] != "b"]
            return result

        self.server.hooks["workspace.create"] = create
        with self.assertRaises(PlacementError) as caught:
            create_after(self.client, "b")
        self.assertEqual((caught.exception.code, caught.exception.stage), (3, "created"))
        self.assertIn(caught.exception.new_id, self.server.ids)
        self.assertEqual(len(self.server.mutations), 1)

    def test_definitive_move_and_focus_failures(self):
        for method, stage in (("workspace.move_block", "created"), ("workspace.focus", "placed")):
            with self.subTest(method=method):
                self.server.hooks.clear()
                self.server.hooks[method] = lambda p: {
                    "code": "denied",
                    "message": "test rejection",
                }
                with self.assertRaises(PlacementError) as caught:
                    create_after(self.client, "b")
                self.assertEqual(caught.exception.code, 3)
                self.assertEqual(caught.exception.stage, stage)
                self.assertIn(caught.exception.new_id, self.server.ids)

    def test_lost_create_never_infers_id_or_retries(self):
        def lost(params):
            self.server.dispatch("workspace.create", params)
            return DROP

        self.server.hooks["workspace.create"] = lost
        code, output, _ = self.explicit("workspace", "--json")
        result = json.loads(output)
        self.assertEqual(code, 4)
        self.assertIsNone(result["new_id"])
        self.assertEqual(len(self.server.mutations), 1)
        self.assertEqual(len(self.server.rows), 4)

    def test_lost_move_response_reconciles_without_retry(self):
        def lost(params):
            self.server.dispatch("workspace.move_block", params)
            return DROP

        self.server.hooks["workspace.move_block"] = lost
        result = move_before(self.client, "c", before="a")
        self.assertEqual(result.status, "complete")
        self.assertEqual(self.server.ids, ["c", "a", "b"])
        self.assertEqual(len(self.server.mutations), 1)

    def test_lost_unapplied_move_reports_uncertainty(self):
        self.server.hooks["workspace.move_block"] = lambda p: DROP
        with self.assertRaises(PlacementError) as caught:
            move_before(self.client, "c", before="a")
        self.assertEqual(caught.exception.code, 4)
        self.assertEqual(len(self.server.mutations), 1)

    def test_small_exhaustive_moves(self):
        for size in range(1, 6):
            ids = [str(i) for i in range(size)]
            for source, target in itertools.product(ids, [*ids, None]):
                self.server.rows = [row(i) for i in ids]
                self.server.requests.clear()
                expected = ids[:]
                if source != target:
                    expected.remove(source)
                    expected.insert(
                        len(expected) if target is None else expected.index(target), source
                    )
                outcome = move_before(self.client, source, before=target)
                self.assertEqual(self.server.ids, expected)
                self.assertEqual(len(self.server.mutations), int(expected != ids))
                self.assertEqual(outcome.code, 0)

    def test_numeric_and_end_rows_above_nine(self):
        self.server.rows = [row(str(i)) for i in range(12)]
        move_before(self.client, "0", number=11)
        self.assertEqual(self.server.ids.index("0"), 9)
        move_before(self.client, "0", number=13)
        self.assertEqual(self.server.ids[-1], "0")

    def test_invalid_numbers_leave_state_unchanged(self):
        for number in (0, -1, 5):
            with self.assertRaises(PlacementError):
                move_before(self.client, "b", number=number)
        self.assertFalse(self.server.mutations)

    def test_frozen_mapping_rejects_order_membership_and_group_changes(self):
        for change in (
            lambda: self.server.rows.reverse(),
            lambda: self.server.rows.pop(),
            lambda: self.server.rows[0].update(
                worktree={"repo_key": "git", "is_linked_worktree": False}
            ),
        ):
            self.server.rows = [row(i) for i in ("a", "b", "c")]
            frozen = read_state(self.client)
            change()
            with self.assertRaises(Changed):
                move_before(self.client, "b", number=1, frozen=frozen)
        self.assertFalse(self.server.mutations)

    def test_label_changes_do_not_reinterpret_id(self):
        frozen = read_state(self.client)
        self.server.rows[0]["label"] = "renamed"
        move_before(self.client, "b", number=1, frozen=frozen)
        self.assertEqual(self.server.ids, ["b", "a", "c"])

    def test_group_projection_rejection_and_standalone_placement(self):
        self.server.rows = [
            row("child", key="repo", linked=True),
            row("a"),
            row("root", key="repo"),
            row("b"),
        ]
        self.assertEqual(
            [r["workspace_id"] for r in read_state(self.client).rows], ["root", "child", "a", "b"]
        )
        for source, before in (("root", "a"), ("a", "child")):
            with self.assertRaises(PlacementError):
                move_before(self.client, source, before=before)
        with self.assertRaises(PlacementError):
            create_after(self.client, "root")
        self.assertFalse(self.server.mutations)
        result = create_after(self.client, "a", focus=False)
        self.assertEqual(
            [r["workspace_id"] for r in read_state(self.client).rows],
            ["root", "child", "a", result.new_id, "b"],
        )
        move_before(self.client, "b", before="a")
        self.assertEqual(
            [r["workspace_id"] for r in read_state(self.client).rows][:4],
            ["root", "child", "b", "a"],
        )

    def test_named_session_and_explicit_source_ignore_inherited_ids(self):
        code, _, _ = self.cli(
            "--socket",
            self.server.path,
            "--source-workspace",
            "b",
            "workspace",
            "--no-focus",
            env={
                "HERDR_SOCKET_PATH": "/bad/socket",
                "HERDR_ACTIVE_WORKSPACE_ID": "stale",
                "HERDR_PANE_ID": "stale",
            },
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.server.ids[1:3], ["b", "new-1"])

    def test_custom_command_context_wins_over_stale_pane(self):
        client, source = capture(
            None,
            None,
            {
                "HERDR_SOCKET_PATH": self.server.path,
                "HERDR_ACTIVE_WORKSPACE_ID": "c",
                "HERDR_PANE_ID": "stale",
            },
        )
        self.assertEqual((client.path, source), (self.server.path, "c"))
        self.assertNotIn("pane.current", [r["method"] for r in self.server.requests])

    def test_moved_pane_resolves_canonical_workspace(self):
        _, source = capture(
            None,
            None,
            {
                "HERDR_SOCKET_PATH": self.server.path,
                "HERDR_PANE_ID": "old:pane",
                "HERDR_WORKSPACE_ID": "stale",
            },
        )
        self.assertEqual(source, "b")

    def test_stale_pane_never_uses_global_focus_or_workspace_fallback(self):
        self.server.pane_workspace = None
        with self.assertRaises(ClientError):
            capture(
                None,
                None,
                {
                    "HERDR_SOCKET_PATH": self.server.path,
                    "HERDR_PANE_ID": "stale",
                    "HERDR_WORKSPACE_ID": "a",
                },
            )
        self.assertFalse(self.server.mutations)

    def test_workspace_only_context_validated(self):
        _, source = capture(
            None, None, {"HERDR_SOCKET_PATH": self.server.path, "HERDR_WORKSPACE_ID": "c"}
        )
        self.assertEqual(source, "c")
        for env in (
            {},
            {"HERDR_SOCKET_PATH": self.server.path},
            {"HERDR_SOCKET_PATH": self.server.path, "HERDR_ACTIVE_WORKSPACE_ID": "missing"},
        ):
            with self.assertRaises(PlacementError):
                capture(None, None, env)
        with self.assertRaises(PlacementError):
            capture(self.server.path, None, {})
        self.assertFalse(self.server.mutations)

    def test_server_version_checked_before_mutations(self):
        self.server.version = "0.9.4"
        code, output, _ = self.explicit("workspace", "--json")
        self.assertEqual(code, 2)
        self.assertIn("unsupported", output)
        self.assertFalse(self.server.mutations)

    def test_reorder_preserves_row_identity_focus_and_process_fields(self):
        self.server.rows[1].update(pane_id="opaque-pane", pid=4321)
        before = {r["workspace_id"]: dict(r) for r in self.server.rows}
        move_before(self.client, "b", before="a")
        self.assertEqual({r["workspace_id"]: r for r in self.server.rows}, before)
        self.assertEqual([r["method"] for r in self.server.mutations], ["workspace.move_block"])

    def test_changed_authoritative_move_result_is_not_fought(self):
        def contended(params):
            result = self.server.dispatch("workspace.move_block", params)
            self.server.rows.reverse()
            return result

        self.server.hooks["workspace.move_block"] = contended
        with self.assertRaises(PlacementError) as caught:
            move_before(self.client, "c", before="a")
        self.assertEqual(caught.exception.code, 4)
        self.assertEqual(len(self.server.mutations), 1)

    def test_quiet_and_durable_failure_diagnostics(self):
        self.assertEqual(self.explicit("workspace", "--quiet")[1], "")
        code, _, error = self.explicit("reorder", "--before-id", "missing")
        self.assertEqual(code, 2)
        self.assertIn("missing", error)
        logs = list(Path(self.tmp.name).rglob("failures.log"))
        self.assertEqual(len(logs), 1)
        self.assertIn("missing", logs[0].read_text())
        self.assertEqual(self.server.requests[-1]["method"], "notification.show")
        for _ in range(140):
            from herdr_next_to_current.placement import Outcome

            failure_log(Outcome("error", "b", error="x" * 12000, code=2))
        self.assertLess(logs[0].stat().st_size, 65537)
        self.assertLess(logs[0].with_name("failures.log.1").stat().st_size, 65537)
        for log in (logs[0], logs[0].with_name("failures.log.1")):
            for line in log.read_text().splitlines():
                self.assertIsInstance(json.loads(line), dict)

    def test_tab_remains_explicit_stub(self):
        code, _, error = self.cli("tab")
        self.assertEqual(code, 2)
        self.assertIn("not implemented", error)
        self.assertFalse(self.server.requests)

    def test_standalone_create_and_move_among_all_interleaved_group_orders(self):
        for ordering in itertools.permutations(("root", "child", "a", "b")):

            def reset(ordering=ordering):
                self.server.rows = [
                    row(i, key="repo" if i in ("root", "child") else None, linked=i == "child")
                    for i in ordering
                ]

            for source in ("a", "b"):
                reset()
                sidebar = [r["workspace_id"] for r in read_state(self.client).rows]
                created = create_after(self.client, source, focus=False)
                sidebar.insert(sidebar.index(source) + 1, created.new_id)
                self.assertEqual([r["workspace_id"] for r in read_state(self.client).rows], sidebar)
                for anchor in ("a", "b", None):
                    reset()
                    sidebar = [r["workspace_id"] for r in read_state(self.client).rows]
                    if source != anchor:
                        sidebar.remove(source)
                        sidebar.insert(
                            len(sidebar) if anchor is None else sidebar.index(anchor), source
                        )
                    move_before(self.client, source, before=anchor)
                    self.assertEqual(
                        [r["workspace_id"] for r in read_state(self.client).rows], sidebar
                    )

    def test_source_becomes_grouped_after_creation(self):
        def create(params):
            result = self.server.dispatch("workspace.create", params)
            self.server.rows[1]["worktree"] = {"repo_key": "repo", "is_linked_worktree": False}
            self.server.rows[2]["worktree"] = {"repo_key": "repo", "is_linked_worktree": True}
            return result

        self.server.hooks["workspace.create"] = create
        with self.assertRaises(PlacementError) as caught:
            create_after(self.client, "b")
        self.assertEqual((caught.exception.code, caught.exception.stage), (3, "created"))
        self.assertIn(caught.exception.new_id, self.server.ids)
        self.assertEqual(len(self.server.mutations), 1)

    def test_lost_focus_response_reconciles(self):
        def lost(params):
            self.server.dispatch("workspace.focus", params)
            return DROP

        self.server.hooks["workspace.focus"] = lost
        self.assertEqual(create_after(self.client, "b").stage, "focused")
        self.assertEqual(len(self.server.mutations), 3)

    def test_source_deleted_during_final_adjacency_check_is_partial(self):
        count = 0

        def listing(params):
            nonlocal count
            count += 1
            if count == 4:
                self.server.rows = [r for r in self.server.rows if r["workspace_id"] != "b"]
            return self.server.dispatch("workspace.list", params)

        self.server.hooks["workspace.list"] = listing
        with self.assertRaises(PlacementError) as caught:
            create_after(self.client, "b")
        self.assertEqual(caught.exception.code, 3)
        self.assertIn(caught.exception.new_id, self.server.ids)

    def test_cli_json_usage_and_noninteractive_reorder(self):
        for arguments in (
            ("reorder", "--before", "oops", "--json"),
            ("reorder", "--before", "1", "--to-end", "--json"),
            ("reorder", "--json"),
        ):
            code, output, _ = self.cli(*arguments)
            self.assertEqual(code, 2)
            self.assertIsNotNone(json.loads(output)["error"])
        self.assertFalse(self.server.requests)

    def test_missing_target_and_source_never_move(self):
        for source, target in (("b", "missing"), ("missing", "a")):
            with self.assertRaises(PlacementError):
                move_before(self.client, source, before=target)
        self.assertFalse(self.server.mutations)

    def test_stale_context_notification_failure_keeps_original_diagnostic(self):
        self.server.hooks["notification.show"] = lambda p: DROP
        code, output, _ = self.cli(
            "workspace",
            "--json",
            env={"HERDR_SOCKET_PATH": self.server.path, "HERDR_ACTIVE_WORKSPACE_ID": "stale"},
        )
        self.assertEqual(code, 2)
        self.assertIn("stale invoking Space", json.loads(output)["error"])
        self.assertEqual(json.loads(output)["source_id"], "stale")
        log = next(Path(self.tmp.name).rglob("failures.log"))
        self.assertIn("stale invoking Space", log.read_text())
        self.assertFalse(self.server.mutations)
        self.assertEqual(self.server.requests[-1]["method"], "notification.show")

    def test_empty_explicit_selectors_never_fall_back_to_environment(self):
        for selectors in (("--source-workspace", ""), ("--socket", "")):
            code, output, _ = self.cli(
                *selectors,
                "workspace",
                "--json",
                env={"HERDR_SOCKET_PATH": self.server.path, "HERDR_ACTIVE_WORKSPACE_ID": "b"},
            )
            self.assertEqual(code, 2)
            self.assertIn("empty", json.loads(output)["error"])
        code, output, _ = self.explicit("reorder", "--before-id", "", "--json")
        self.assertEqual(code, 2)
        self.assertIn("empty", json.loads(output)["error"])
        self.assertFalse(self.server.requests)

    def test_create_response_cannot_name_an_existing_space(self):
        self.server.hooks["workspace.create"] = lambda p: {
            "type": "workspace_created",
            "workspace": {"workspace_id": "c"},
        }
        with self.assertRaises(PlacementError) as caught:
            create_after(self.client, "b")
        self.assertEqual(caught.exception.code, 4)
        self.assertIsNone(caught.exception.new_id)
        self.assertEqual(len(self.server.mutations), 1)
        self.assertEqual(self.server.ids, ["a", "b", "c"])

    def test_focus_timeout_with_failed_reconciliation_is_uncertain(self):
        def lost(params):
            self.server.hooks["workspace.list"] = lambda p: DROP
            return DROP

        self.server.hooks["workspace.focus"] = lost
        with self.assertRaises(PlacementError) as caught:
            create_after(self.client, "b")
        self.assertEqual(caught.exception.code, 4)
        self.assertEqual(caught.exception.stage, "placed")
        self.assertIsNotNone(caught.exception.new_id)

    def test_sidebar_adjacency_is_a_noop_even_with_interleaved_raw_group_members(self):
        self.server.rows = [
            row("root", key="repo"),
            row("a"),
            row("child", key="repo", linked=True),
            row("b"),
        ]
        self.assertEqual(move_before(self.client, "a", before="b").status, "no-op")
        self.assertFalse(self.server.mutations)
        self.server.rows.pop()
        created = create_after(self.client, "a", focus=False)
        self.assertEqual(
            [r["workspace_id"] for r in read_state(self.client).rows],
            ["root", "child", "a", created.new_id],
        )
        self.assertEqual([r["method"] for r in self.server.mutations], ["workspace.create"])
