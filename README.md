# herdr-next-to-current

Create a Herdr **Space immediately below the invoking Space**, or move the invoking
Space before a numbered destination. Herdr's socket API calls Spaces `workspaces`.
Requires Linux/WSL, Python 3.11+, and Herdr **0.9.3 / protocol 22**. There are no
runtime dependencies beyond Python's standard library, including `curses`.

```sh
herdr-next-to-current workspace
herdr-next-to-current workspace --label review --cwd ~/project --no-focus
herdr-next-to-current reorder
herdr-next-to-current reorder --before 2
herdr-next-to-current reorder --before-id WORKSPACE_ID --json
herdr-next-to-current reorder --to-end
```

Creation preserves Herdr's directory policy unless `--cwd` supplies an explicit
absolute directory. It creates without focus, places and verifies the returned
Space ID, then focuses it unless `--no-focus` is set. Public focus is session-wide.
The source is captured once; queued creations from the same source appear newest
first. Existing panes and processes survive reordering. Tab creation remains an
explicit, unimplemented stub.

The popup numbers fully expanded sidebar rows, includes the current Space, and
adds an `N+1` end-of-list choice. Type multiple digits and Enter to move; use
Backspace, PgUp/PgDn, `r` to refresh, or Esc/`q` to cancel. Changed membership,
order, or grouping clears the selection and requires another choice. Labels are
not identities. Git worktree groups stay visible with an explanation; grouped
sources and destinations are unavailable in this release.

## Source and session

Explicit selectors take precedence. An explicit socket requires an explicit source:

```sh
herdr-next-to-current --socket /path/to/session.sock --source-workspace ID workspace
```

Custom shell/popup commands use `HERDR_ACTIVE_WORKSPACE_ID` with
`HERDR_SOCKET_PATH`. Pane commands resolve `HERDR_PANE_ID` through `pane.current`,
including moved panes; workspace-only context uses `HERDR_WORKSPACE_ID`. Stale or
missing context fails without choosing server-wide focus. Outside Herdr, supply
both explicit selectors. Options `--socket` and `--source-workspace` precede the
subcommand; `--json`, `--quiet`, and workflow options follow it.

## Installation

Requires [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/):

```sh
git clone https://github.com/vimkim/herdr-next-to-current.git ~/gh/herdr-next-to-current
cd ~/gh/herdr-next-to-current
just sync
```

`just sync` runs `uv tool install --reinstall .` from the primary `main` checkout.
This regular installation runs without the source checkout or its `.venv`.
Run sync after source changes, including changes without a version bump.
The next sync also converts an existing editable installation. Use `uv run` for development.
An isolated install can use `UV_TOOL_DIR` and `UV_TOOL_BIN_DIR` with
`uv tool install --reinstall .` without replacing your normal command.

Use `uv tool dir --bin` to locate the commands, or `UV_TOOL_BIN_DIR` to select another directory.
Run `uv tool update-shell` if that directory is absent from PATH.
Uninstall with `uv tool uninstall herdr-next-to-current`.
Tool installation resolves dependencies separately from the project's `uv.lock`.
This package has no third-party runtime dependencies.

Chezmoi integration is prepared separately: Alt+C creates quietly; Alt+Shift+C
opens the popup; Alt+W, existing workspace up/down helpers, and tab bindings stay
available. Source changes disable native creation so it cannot intercept Alt+C.
The bootstrap preserves occupied/dirty/topic checkouts and returns failure for
retryable skipped installs. Daily updates require clean primary `main` tracking
`origin/main` with the expected GitHub origin, and skip ahead/diverged checkouts.
See [integration and verification notes](docs/verification.md) before rollout.

## Results

Human output is the default. `--quiet` suppresses success; `--json` emits status,
source ID, new ID when known, completed stage, error, and exit code.

| Exit | Meaning |
| --- | --- |
| 0 | Complete, already placed, or cancelled before a mutation |
| 2 | Usage/context/group/unsupported-server error or pre-mutation failure |
| 3 | New Space preserved; placement or focus is incomplete |
| 4 | A mutation's outcome could not be established; inspect before retrying |

A lost create response never causes a retry or an inferred new ID. A lost move
response can be reconciled by reading state. Other clients can still modify the
session despite the helper's bounded per-socket lock; the helper does not fight
them with repeated moves. Incomplete creations are never closed automatically.

Failures are logged under `$XDG_STATE_HOME/herdr-next-to-current/` (default
`~/.local/state/herdr-next-to-current/`). `failures.log` and one rotated copy are
each bounded to 64 KiB. Notifications include the log location when Herdr can
accept them; notification failure does not replace the original error. Failed
popup moves remain visible, and an unresolved uncertain move still exits 4 if
cancelled afterward.

## Development

```sh
just check  # lint, fake Unix socket / PTY tests, wheel and source build
HERDR_LIVE_TEST=1 uv run python -m unittest tests.test_live -v
```

The opt-in live test starts its own Herdr server, two PTY clients, config, state,
and sockets in a temporary directory. It never selects your working session.
It exercises real shortcut delivery and popup context as well as cwd, placement,
focus, reorder, and pane/process identity. Host terminal shortcut interception
still needs a check on the actual client terminal.

[PLAN.md](PLAN.md) records the implementation contract; the
[API evidence](docs/workspace-order-evidence.md) explains the versioned sidebar
projection and ID-anchored move operation.
