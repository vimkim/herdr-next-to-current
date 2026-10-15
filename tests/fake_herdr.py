"""A real Unix socket test server with controllable mutation failures."""

import copy
import json
import socketserver
import tempfile
import threading
from pathlib import Path

DROP = object()


def row(workspace_id, *, key=None, linked=False):
    result = {
        "workspace_id": workspace_id,
        "label": "duplicate label",
        "focused": False,
        "pane_count": 1,
        "tab_count": 1,
        "active_tab_id": workspace_id + ":t1",
    }
    if key:
        result["worktree"] = {"repo_key": key, "is_linked_worktree": linked}
    return result


class FakeHerdr:
    def __init__(self, ids=("a", "b", "c")):
        self.rows = [row(item) for item in ids]
        self.rows[0]["focused"] = True
        self.requests = []
        self.hooks = {}
        self.version, self.protocol = "0.9.3", 22
        self.pane_workspace = "b"
        self.serial = 0
        self.guard = threading.RLock()
        self.tmp = tempfile.TemporaryDirectory(prefix="hntc-")
        self.path = str(Path(self.tmp.name) / "api.sock")
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                request = json.loads(self.rfile.readline())
                with owner.guard:
                    owner.requests.append(request)
                    method, params = request["method"], request["params"]
                    hook = owner.hooks.get(method)
                    result = hook(params) if hook else None
                    if result is None:
                        result = owner.dispatch(method, params)
                    if result is DROP:
                        return
                    response = {
                        "id": request["id"],
                        "error" if "code" in result else "result": result,
                    }
                    self.wfile.write(json.dumps(response).encode() + b"\n")

        self.server = socketserver.ThreadingUnixStreamServer(self.path, Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}
        )
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    @property
    def ids(self):
        return [r["workspace_id"] for r in self.rows]

    @property
    def mutations(self):
        return [
            r
            for r in self.requests
            if r["method"] in ("workspace.create", "workspace.move_block", "workspace.focus")
        ]

    def dispatch(self, method, params):
        if method == "ping":
            return {"type": "pong", "version": self.version, "protocol": self.protocol}
        if method == "workspace.list":
            return {"type": "workspace_list", "workspaces": copy.deepcopy(self.rows)}
        if method == "pane.current":
            if self.pane_workspace is None:
                return {"code": "not_found", "message": "stale pane"}
            return {"type": "pane_current", "pane": {"workspace_id": self.pane_workspace}}
        if method == "workspace.create":
            self.serial += 1
            new = row(f"new-{self.serial}")
            self.rows.append(new)
            return {"type": "workspace_created", "workspace": new, "tab": {}, "root_pane": {}}
        if method == "workspace.move_block":
            source = params["workspace_ids"][0]
            anchor = params.get("before_workspace_id")
            moved = next(r for r in self.rows if r["workspace_id"] == source)
            self.rows.remove(moved)
            self.rows.insert(len(self.rows) if anchor is None else self.ids.index(anchor), moved)
            return self.dispatch("workspace.list", {})
        if method == "workspace.focus":
            for record in self.rows:
                record["focused"] = record["workspace_id"] == params["workspace_id"]
            return {
                "type": "workspace_info",
                "workspace": next(r for r in self.rows if r["focused"]),
            }
        if method == "notification.show":
            return {"type": "notification_show", "shown": True}
        raise AssertionError(method)
