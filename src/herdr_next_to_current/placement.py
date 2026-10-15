"""Source identity, sidebar projection, and verified create/move workflows."""

import fcntl
import hashlib
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .client import Client, ClientError


class PlacementError(Exception):
    def __init__(self, message, *, code=2, stage="validated", new_id=None):
        super().__init__(message)
        self.code, self.stage, self.new_id = code, stage, new_id


class Changed(PlacementError):
    """The picker mapping changed; require a new choice."""


@dataclass
class Outcome:
    status: str
    source_id: str | None
    new_id: str | None = None
    stage: str = "validated"
    error: str | None = None
    code: int = 0


@dataclass(frozen=True)
class State:
    raw: tuple[dict, ...]

    @property
    def ids(self):
        return [row["workspace_id"] for row in self.raw]

    @property
    def groups(self):
        members = {}
        for row in self.raw:
            if tree := row.get("worktree"):
                members.setdefault(tree["repo_key"], []).append(row)
        return {
            key: rows
            for key, rows in members.items()
            if len(rows) >= 2 and any(not r["worktree"]["is_linked_worktree"] for r in rows)
        }

    @property
    def rows(self):
        groups, emitted, rows = self.groups, set(), []
        for row in self.raw:
            key = (row.get("worktree") or {}).get("repo_key")
            if key not in groups:
                rows.append(row)
            elif key not in emitted:
                emitted.add(key)
                members = groups[key]
                parent = next(r for r in members if not r["worktree"]["is_linked_worktree"])
                rows.extend([parent, *(r for r in members if r is not parent)])
        return rows

    @property
    def signature(self):
        # Labels/focus may change without invalidating the displayed numeric mapping.
        return tuple(
            (
                r["workspace_id"],
                (r.get("worktree") or {}).get("repo_key"),
                (r.get("worktree") or {}).get("is_linked_worktree"),
            )
            for r in self.raw
        )

    def standalone(self, workspace_id):
        row = next((r for r in self.raw if r["workspace_id"] == workspace_id), None)
        if row is None:
            raise PlacementError(f"Space {workspace_id!r} no longer exists; refresh context")
        if (row.get("worktree") or {}).get("repo_key") in self.groups:
            raise PlacementError(f"Space {workspace_id!r} belongs to a Git worktree group")
        return row


def parse_state(result):
    rows = result.get("workspaces")
    if not isinstance(rows, list):
        raise ClientError("invalid workspace list")
    ids = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("workspace_id"), str):
            raise ClientError("invalid workspace record")
        if not row["workspace_id"] or row["workspace_id"] in ids:
            raise ClientError("empty or duplicate workspace ID")
        ids.add(row["workspace_id"])
        if not isinstance(row.get("label"), str):
            raise ClientError("invalid workspace label")
        tree = row.get("worktree")
        if tree is not None and (
            not isinstance(tree, dict)
            or not isinstance(tree.get("repo_key"), str)
            or not isinstance(tree.get("is_linked_worktree"), bool)
        ):
            raise ClientError("invalid worktree metadata")
    return State(tuple(rows))


def read_state(client):
    return parse_state(client.call("workspace.list", {}, "workspace_list"))


def capture(socket_path, source_id, env, *, client=None):
    if socket_path is not None and not source_id:
        raise PlacementError("--socket requires --source-workspace", stage="context")
    path = socket_path or env.get("HERDR_SOCKET_PATH")
    if not path:
        raise PlacementError(
            "provide --socket and --source-workspace outside Herdr", stage="context"
        )
    client = client or Client(path)
    client.validate()
    if source_id:
        source = source_id
    elif env.get("HERDR_ACTIVE_WORKSPACE_ID"):
        source = env["HERDR_ACTIVE_WORKSPACE_ID"]
    elif env.get("HERDR_PANE_ID"):
        pane = client.call(
            "pane.current", {"caller_pane_id": env["HERDR_PANE_ID"]}, "pane_current"
        ).get("pane")
        if not isinstance(pane, dict) or not isinstance(pane.get("workspace_id"), str):
            raise PlacementError("pane.current returned no workspace identity", stage="context")
        source = pane["workspace_id"]
    else:
        source = env.get("HERDR_WORKSPACE_ID")
    if not source:
        raise PlacementError("missing invoking Space; provide --source-workspace", stage="context")
    state = read_state(client)
    if source not in state.ids:
        raise PlacementError(
            f"stale invoking Space {source!r}; invoke from a live Space", stage="context"
        )
    return client, source


@contextmanager
def mutation_lock(client, timeout=3.0):
    # Resolve aliases so two spellings of the same socket share a lock.
    key = hashlib.sha256(os.fsencode(os.path.realpath(client.path))).hexdigest()
    directory = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    directory = directory / "herdr-next-to-current"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / f"{key}.lock").open("a", encoding="utf-8") as lock:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise PlacementError(
                        "another helper is busy; retry after it finishes"
                    ) from None
                time.sleep(0.025)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def planned_ids(ids, source, before):
    if source == before:
        return list(ids)
    remaining = [item for item in ids if item != source]
    remaining.insert(len(remaining) if before is None else remaining.index(before), source)
    return remaining


def _move(client, state, source, before, *, expected_sidebar=None):
    sidebar = [r["workspace_id"] for r in state.rows]
    if expected_sidebar is None:
        expected_sidebar = planned_ids(sidebar, source, before)
    # Interleaved raw group members can sit between visually adjacent standalone rows.
    if expected_sidebar == sidebar:
        return False
    expected = planned_ids(state.ids, source, before)
    if expected == state.ids:
        return False
    params = {"workspace_ids": [source]}
    if before is not None:
        params["before_workspace_id"] = before
    try:
        response = client.call("workspace.move_block", params, "workspace_list", mutation=True)
    except ClientError as error:
        if not error.uncertain:
            raise
        try:
            reconciled = read_state(client)
        except ClientError:
            raise error from None
        if reconciled.ids != expected:
            raise error
        response = {"workspaces": list(reconciled.raw)}
    try:
        returned = parse_state(response)
        final = read_state(client)
    except ClientError as error:
        raise PlacementError(str(error), code=4, stage="move_sent") from error
    if returned.ids != expected or final.ids != expected:
        raise PlacementError(
            "order changed during movement; inspect the list before retrying",
            code=4,
            stage="move_sent",
        )
    signatures = dict(zip(state.ids, state.signature, strict=True))
    expected_signature = tuple(signatures[item] for item in expected)
    if returned.signature != expected_signature or final.signature != expected_signature:
        raise PlacementError(
            "Git worktree groups changed during movement", code=4, stage="move_sent"
        )
    if [r["workspace_id"] for r in final.rows] != expected_sidebar:
        raise PlacementError("sidebar placement could not be verified", code=4, stage="move_sent")
    return True


def create_after(client, source, *, label=None, cwd=None, focus=True):
    new_id, stage = None, "validated"
    try:
        with mutation_lock(client):
            initial = read_state(client)
            initial.standalone(source)
            params = {"source_workspace_id": source, "focus": False}
            if label is not None:
                params["label"] = label
            if cwd is not None:
                params["cwd"] = str(Path(cwd).expanduser().resolve())
            result = client.call("workspace.create", params, "workspace_created", mutation=True)
            workspace = result.get("workspace")
            if not isinstance(workspace, dict) or not isinstance(
                workspace.get("workspace_id"), str
            ):
                raise ClientError("create response has no workspace ID", uncertain=True)
            new_id, stage = workspace["workspace_id"], "created"
            if not new_id or new_id in initial.ids:
                new_id = None
                raise ClientError("create response has an invalid workspace ID", uncertain=True)
            state = read_state(client)
            state.standalone(source)
            state.standalone(new_id)
            others = [item for item in state.ids if item != new_id]
            index = others.index(source) + 1
            before = others[index] if index < len(others) else None
            sidebar = [r["workspace_id"] for r in state.rows if r["workspace_id"] != new_id]
            sidebar.insert(sidebar.index(source) + 1, new_id)
            _move(client, state, new_id, before, expected_sidebar=sidebar)
            rows = [r["workspace_id"] for r in read_state(client).rows]
            if (
                source not in rows
                or new_id not in rows
                or rows.index(new_id) != rows.index(source) + 1
            ):
                raise PlacementError("new Space is no longer adjacent", code=3)
            stage = "placed"
            if focus:
                try:
                    result = client.call(
                        "workspace.focus", {"workspace_id": new_id}, "workspace_info", mutation=True
                    )
                except ClientError as error:
                    if not error.uncertain:
                        raise
                    try:
                        rows = read_state(client).raw
                    except ClientError:
                        raise error from None
                    if not any(r["workspace_id"] == new_id and r.get("focused") for r in rows):
                        raise error
                else:
                    row = result.get("workspace")
                    if (
                        not isinstance(row, dict)
                        or row.get("workspace_id") != new_id
                        or row.get("focused") is not True
                    ):
                        raise ClientError(
                            "focus response did not confirm the new Space", uncertain=True
                        )
                stage = "focused"
        return Outcome("complete", source, new_id, stage)
    except (ClientError, PlacementError, OSError) as error:
        code = 4 if getattr(error, "uncertain", False) else (3 if new_id else 2)
        if isinstance(error, PlacementError) and error.code == 4:
            code = 4
        raise PlacementError(str(error), code=code, stage=stage, new_id=new_id) from error


def move_before(client, source, *, before=None, number=None, frozen=None):
    with mutation_lock(client):
        state = read_state(client)
        if frozen is not None and state.signature != frozen.signature:
            raise Changed("Space order or groups changed; choose a number again")
        state.standalone(source)
        if number is not None:
            if number < 1 or number > len(state.rows) + 1:
                raise PlacementError(f"choose a number from 1 to {len(state.rows) + 1}")
            before = state.rows[number - 1]["workspace_id"] if number <= len(state.rows) else None
        if before is not None:
            state.standalone(before)
        try:
            changed = _move(client, state, source, before)
        except ClientError as error:
            raise PlacementError(
                str(error), code=4 if error.uncertain else 2, stage="move_sent"
            ) from error
    return Outcome("complete" if changed else "no-op", source, stage="placed")
