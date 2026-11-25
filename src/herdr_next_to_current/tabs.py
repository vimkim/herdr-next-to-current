"""Captured tab context and verified adjacent creation on Herdr 0.9.3 and 0.9.5."""

from dataclasses import dataclass
from pathlib import Path

from .client import Client, ClientError
from .placement import Outcome, PlacementError, mutation_lock


@dataclass(frozen=True)
class TabState:
    rows: tuple[dict, ...]

    @property
    def ids(self):
        return [row["tab_id"] for row in self.rows]

    def require(self, tab_id):
        if tab_id not in self.ids:
            raise PlacementError(f"tab {tab_id!r} no longer exists in the invoking Space")


def parse_tabs(result, workspace):
    rows = result.get("tabs")
    if not isinstance(rows, list):
        raise ClientError("invalid tab list")
    ids = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("tab_id"), str)
            or not row["tab_id"]
            or row["tab_id"] in ids
            or row.get("workspace_id") != workspace
            or not isinstance(row.get("label"), str)
            or not isinstance(row.get("focused"), bool)
        ):
            raise ClientError("invalid tab record or workspace membership")
        ids.add(row["tab_id"])
    return TabState(tuple(rows))


def read_tabs(client, workspace):
    return parse_tabs(client.call("tab.list", {"workspace_id": workspace}, "tab_list"), workspace)


def capture_tab(socket_path, workspace, source, env, *, client=None):
    if (socket_path is not None or workspace is not None or source is not None) and not (
        workspace and source
    ):
        raise PlacementError(
            "tab selectors require both --source-workspace and --source-tab", stage="context"
        )
    path = socket_path or env.get("HERDR_SOCKET_PATH")
    if not path:
        raise PlacementError(
            "provide --socket, --source-workspace and --source-tab outside Herdr", stage="context"
        )
    client = client or Client(path)
    client.validate()
    if source is not None:
        pass
    elif env.get("HERDR_ACTIVE_WORKSPACE_ID") or env.get("HERDR_ACTIVE_TAB_ID"):
        workspace = env.get("HERDR_ACTIVE_WORKSPACE_ID")
        source = env.get("HERDR_ACTIVE_TAB_ID")
    elif env.get("HERDR_PANE_ID"):
        pane = client.call(
            "pane.current", {"caller_pane_id": env["HERDR_PANE_ID"]}, "pane_current"
        ).get("pane")
        if not isinstance(pane, dict):
            raise PlacementError("pane.current returned no tab context", stage="context")
        workspace, source = pane.get("workspace_id"), pane.get("tab_id")
    else:
        workspace, source = env.get("HERDR_WORKSPACE_ID"), env.get("HERDR_TAB_ID")
    if not isinstance(workspace, str) or not workspace or not isinstance(source, str) or not source:
        raise PlacementError("missing invoking Space or tab context", stage="context")
    read_tabs(client, workspace).require(source)
    return client, workspace, source


def create_tab_after(client, workspace, source, *, label=None, cwd=None, env=None, focus=True):
    new_id, stage = None, "validated"
    try:
        with mutation_lock(client):
            initial = read_tabs(client, workspace)
            initial.require(source)
            params = {"workspace_id": workspace, "focus": False}
            if label is not None:
                params["label"] = label
            if cwd is not None:
                params["cwd"] = str(Path(cwd).expanduser().resolve())
            if env:
                params["env"] = dict(env)
            result = client.call("tab.create", params, "tab_created", mutation=True)
            tab = result.get("tab")
            if (
                not isinstance(tab, dict)
                or not isinstance(tab.get("tab_id"), str)
                or not tab["tab_id"]
                or tab["tab_id"] in initial.ids
            ):
                raise ClientError("create response has no valid new tab ID", uncertain=True)
            new_id, stage = tab["tab_id"], "created"
            if tab.get("workspace_id") != workspace:
                raise PlacementError("new tab is outside the invoking Space")
            state = read_tabs(client, workspace)
            state.require(source)
            state.require(new_id)
            expected = [item for item in state.ids if item != new_id]
            expected.insert(expected.index(source) + 1, new_id)
            if state.ids != expected:
                # The insertion slot refers to the list BEFORE removal of the moved tab.
                params = {"tab_id": new_id, "insert_index": state.ids.index(source) + 1}
                try:
                    response = client.call("tab.move", params, "tab_list", mutation=True)
                except ClientError as error:
                    if not error.uncertain:
                        raise
                    try:
                        reconciled = read_tabs(client, workspace)
                    except ClientError:
                        raise error from None
                    if reconciled.ids != expected:
                        raise error
                    response = {"tabs": list(reconciled.rows)}
                try:
                    returned = parse_tabs(response, workspace)
                    final = read_tabs(client, workspace)
                except ClientError as error:
                    raise ClientError(str(error), uncertain=True) from error
                if returned.ids != expected or final.ids != expected:
                    raise PlacementError(
                        "tab order changed during movement; inspect before retrying", code=4
                    )
            final = read_tabs(client, workspace)
            if (
                source not in final.ids
                or new_id not in final.ids
                or (final.ids.index(new_id) != final.ids.index(source) + 1)
            ):
                raise PlacementError("new tab is no longer adjacent")
            stage = "placed"
            if focus:
                try:
                    response = client.call(
                        "tab.focus", {"tab_id": new_id}, "tab_info", mutation=True
                    )
                except ClientError as error:
                    if not error.uncertain:
                        raise
                    try:
                        focused = read_tabs(client, workspace)
                    except ClientError:
                        raise error from None
                    if not any(r["tab_id"] == new_id and r["focused"] for r in focused.rows):
                        raise error
                    tab = next(r for r in focused.rows if r["tab_id"] == new_id)
                else:
                    tab = response.get("tab")
                if (
                    not isinstance(tab, dict)
                    or tab.get("tab_id") != new_id
                    or tab.get("workspace_id") != workspace
                    or tab.get("focused") is not True
                ):
                    raise ClientError("focus response did not confirm the new tab", uncertain=True)
                stage = "focused"
        return Outcome("complete", source, new_id, stage)
    except KeyboardInterrupt as error:
        # Creation may have completed before the interrupt; retain its returned identity.
        raise PlacementError("interrupted", code=4, stage=stage, new_id=new_id) from error
    except (ClientError, PlacementError, OSError) as error:
        code = 4 if getattr(error, "uncertain", False) else (3 if new_id else 2)
        if isinstance(error, PlacementError) and error.code == 4:
            code = 4
        raise PlacementError(str(error), code=code, stage=stage, new_id=new_id) from error
