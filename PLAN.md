# Herdr Spaces creation and ordering plan

Updated: 2026-10-23. The two Space workflows and adjacent tab creation are implemented.
This document retains the behavior contract; see [verification and local rollout](docs/verification.md)
for execution evidence and the separately prepared chezmoi integration.

Here, a **Space** means an entry in Herdr's **Spaces sidebar**. Herdr's public
socket interface and CLI call a Space a `workspace`; the code and command names
below use that spelling. Agents run inside panes and have a separate listing.

Use the existing **Python uv project, `herdr-next-to-current`**, for two workflows:
create a Space immediately below the invoking Space, and open a numbered TUI
that moves the invoking Space immediately before the chosen Space.
Herdr already provides the required socket operations. Python's standard library
is sufficient, including `curses` for this small TUI; no Rust build or native
plugin is needed for the first release.

## Scope and prior decisions

Keep the established distribution, console command, Python package
`herdr_next_to_current`, canonical checkout `~/gh/herdr-next-to-current`, Python
3.11 minimum, Linux/WSL support, and regular uv tool installation from merged `main`.
The numbered TUI expands the earlier adjacent-creation-only scope.
The 2026-10-23 tab milestone supersedes the original tab exclusion.
Preserve the existing workspace up/down helper and tab movement bindings.

## Adjacent tab creation

`herdr-next-to-current tab` creates immediately to the right of the invoking tab
in the same workspace. It preserves `--label`, `--cwd`, `--no-focus`, `--json`,
and `--quiet`. It focuses the new tab by default. A final source gets a final tab.

Capture workspace and tab IDs before acquiring the existing per-socket mutation lock.
Explicit context requires `--source-workspace` and `--source-tab` together.
An explicit socket also requires both. Custom commands require both
`HERDR_ACTIVE_WORKSPACE_ID` and `HERDR_ACTIVE_TAB_ID`, ahead of inherited pane context.
Pane invocation resolves both IDs through one `pane.current` call.
Workspace-only environment requires both `HERDR_WORKSPACE_ID` and `HERDR_TAB_ID`.
Validate membership before creation and again before movement. Never substitute global focus.

Create once with the captured `workspace_id` and `focus:false`.
Keep the returned tab ID. Omit cwd unless explicitly supplied.
Herdr's directory policy then uses the captured workspace's backend active pane,
which can differ from the invoking tab. An explicit cwd overrides that policy.

Read fresh order through `tab.list(workspace_id=...)`.
Use `tab.move` with the insertion slot immediately after the captured source.
That zero-based slot refers to the list before removal of the moved tab.
Skip movement if already adjacent. Verify returned and fresh order by stable IDs,
including the relative order of unrelated tabs. Verify adjacency before focus.
Only tab order changes. Workspace groups do not restrict this workflow.

The existing partial-failure contract applies. Preserve a known created tab.
Never retry an uncertain create or infer its ID from a list difference.
Reconcile lost move and focus responses with reads, without repeating mutations.
Report conflicting order and stop. Creation, placement, and focus remain separate operations.
See [tab API evidence](docs/tab-order-evidence.md) and [verification](docs/verification.md).

## Space invariants

Retain strict source resolution, no silent selection of server-wide focus, and
default focus after successful creation with `--no-focus` available. Public focus
is session-wide. Source identity stays fixed throughout a command.

The initial group policy retains the earlier restriction: adjacent creation
rejects sources belonging to a displayed Git worktree group, including its root.
The proposed reorder policy likewise rejects a grouped source or destination.
Show grouped rows with an explanation rather than hiding or renumbering them.
Moving whole groups requires a separate explicit contract; the raw movement
operation does not enforce group boundaries. Group support is a deferred
extension. The inspected working session has no grouped Spaces, so this limit
does not affect its current Spaces.

Current API and source evidence is collected in
[workspace-order-evidence.md](docs/workspace-order-evidence.md). Both the installed
CLI and running server reported **0.9.3, protocol 22** during this investigation.
No live workspace was created, moved, focused, or closed.

## User experience

| Invocation | Planned behavior |
| --- | --- |
| `herdr-next-to-current workspace` | Create below the invoking workspace, then focus the new workspace |
| `herdr-next-to-current workspace --label review --cwd ~/project` | Same placement, with explicit label and directory |
| `herdr-next-to-current workspace --no-focus` | Same placement, without requesting a focus change |
| `herdr-next-to-current reorder` | Open the numbered move TUI |
| `herdr-next-to-current reorder --before 2` | Move before row 2 from a fresh list, without a TUI |
| `herdr-next-to-current reorder --before-id WORKSPACE_ID` | Move before a stable ID, suitable for automation |
| `herdr-next-to-current reorder --to-end` | Move to the end |

Use mutually exclusive destination options. Add `--json` for noninteractive
commands. Global `--socket PATH` and `--source-workspace ID` support explicit
automation; an explicit socket requires an explicit source workspace.

Example TUI:

```text
Move Space: api

   1  dotfiles
   2  CUBRID
 > 3  api             current
   4  logs
   5  [end of list]

Insert current Space before number: _
Enter: move   Esc/q: cancel   r: refresh   PgUp/PgDn: scroll
```

Typing `2` and Enter produces `dotfiles, api, CUBRID, logs`. The same `api`
workspace, panes, processes, and focus remain; only its order changes. Close the
popup after success. A failed move stays visible with an actionable message.

Indices are **one-based displayed row numbers**, independent of workspace IDs.
Include the current row so other rows retain their numbers. Selecting the current
row or an already adjacent destination succeeds without a mutation. The extra
`N+1` row is an insertion choice, not a real workspace index, and allows moving
to the end. Accept multiple digits, Backspace, resize, and lists longer than the
popup. Reject empty input, zero, negative values, and out-of-range numbers.

Freeze the displayed number-to-ID mapping until refresh or submission. On Enter,
fetch fresh state; if order, membership, or grouping changed, refresh the rows,
clear the input, and require a new selection. Labels can update without changing
identity. Never silently reinterpret a typed number against a different list.
Do not hold a mutation lock while waiting for keyboard input.

## Source and session selection

Capture the socket and source before opening the TUI or waiting for a lock:

1. Explicit selectors win; validate the source on the explicitly selected socket.
2. Herdr custom commands provide `HERDR_ACTIVE_WORKSPACE_ID` and the invoking
   socket. Prefer that captured workspace context over inherited pane variables.
3. A command typed in a pane uses `HERDR_PANE_ID` with
   `pane.current(caller_pane_id=...)`, resolving the canonical workspace even if a
   pane has moved. Validate available workspace-only context when no pane ID is
   available; do not replace a failed pane resolution with global focus.
4. Missing, inconsistent, or stale context fails before mutation. Outside Herdr,
   require both explicit socket and source. Do not guess the default socket,
   parse ID prefixes, or use whichever workspace another client is viewing.

The investigating shell actually has stale caller IDs while another workspace is
focused. This is a required failure case, not a reason to infer a new source.
Scope one invocation to one server socket. Combined views of multiple saved
machines and remote socket bridging are outside the first release.

## Ordering operations

Use [`workspace.move_block`](https://herdr.dev/docs/socket-api/#raw-methods) with
a single workspace ID and an optional `before_workspace_id`. The server resolves
the IDs and applies that one move atomically. This avoids `workspace.move`'s
pre-removal insertion-slot arithmetic. An absent anchor means the end.

For example, moving `api` before `CUBRID` sends:

```json
{"id":"move-1","method":"workspace.move_block","params":{"workspace_ids":["api-id"],"before_workspace_id":"cubrid-id"}}
```

The UI numbers never cross this mutation interface. Names are labels only; use
the IDs received from Herdr, rather than constructing IDs from labels.

For **reorder**, validate the frozen source, selected target, group policy, and
latest order; recognize no-ops; send one ID-anchored move. Check its authoritative
returned list for the requested placement and preservation of the other rows'
relative order. Request no focus change. A final read can detect subsequent
contention; it cannot prevent another client from moving things again. Do not
automatically fight that client by repeatedly moving the source back.

For **creation below the source**:

1. Validate the source and group policy, then create with `focus:false` and
   `source_workspace_id` set to the captured source. Pass a label when supplied.
2. An explicit `--cwd` becomes an absolute path. Otherwise omit `cwd` so Herdr
   applies its configured directory policy to the specified source workspace.
   This does not pin a particular invoking pane if clients select different
   tabs/panes within that workspace; use `--cwd` when that exact directory matters.
3. Keep the created workspace ID from the response. Read fresh ordered state
   and revalidate the source and its group status. If it disappeared or became
   grouped, preserve the new workspace and report incomplete placement. Otherwise
   identify the source's successor with the new workspace excluded. Move the new
   ID before that successor, or to the end when absent. Skip movement when the
   workspace is already adjacent.
4. Verify adjacency, then focus the new ID unless `--no-focus` was requested.
   Do not close the new workspace if placement or focus fails.

Creation and placement are separate server operations, so an appended workspace
may briefly appear. Atomic create-at-position would need a Herdr change. A
per-socket advisory lock serializes this helper's short mutation workflows, with
a bounded wait; unrelated clients can still change the session. Capture source
identity before the lock. Two queued creates captured from B produce
`B, NEW2, NEW1`; a later trigger captured from NEW1 naturally creates a chain.

With Git worktree groups present, Herdr's flat storage order can differ from
sidebar order. Build picker rows from the version-checked sidebar projection,
keeping roots and children together; never assume raw list indices are visible
sidebar indices. Use the picker's own fully expanded numbering, regardless of
the client's collapsed sidebar state. Reject moves involving grouped rows under
the initial policy.
Test standalone placement alongside groups as well as sessions without groups.

## Module design

Keep the external interface at the CLI. Four small implementation files suffice:

```text
src/herdr_next_to_current/
  cli.py          # arguments, captured context, result formatting and exit codes
  client.py       # Unix socket request/response transport
  placement.py    # validated source, order planning, create/move/verify workflows
  tui.py          # curses rendering, numeric input and cancellation
```

`placement.py` is the deep module: the CLI and TUI ask it to create after a source
or move a source before an anchor, without knowing index adjustment, group
validation, partial-failure recovery, or focus sequencing. Keep order calculation
pure and socket transport supplied by the caller. Test workflows through this
interface and through the CLI with a fake Unix socket server. Avoid a general
plugin framework, daemon, database, event subscription cache, or interchangeable
backend layer for this two-command tool.

The client opens one connection per ordinary request, uses newline-delimited
JSON, verifies request IDs and result types, and applies bounded I/O and response
sizes. Do not implicitly retry mutations. Validate the running server's metadata
and required operations; matching the locally installed CLI version alone is
insufficient. Target verified 0.9.3 behavior initially and report unsupported
servers explicitly rather than silently switching to numeric moves.

## Results and failures

| Outcome | Exit | Behavior |
| --- | --- | --- |
| Complete, no-op, or interactive cancel | 0 | Normal success; cancel changes nothing |
| Usage, context, unsupported group, or pre-mutation failure | 2 | Explain the correction; leave state untouched |
| New workspace exists, but placement/focus is incomplete | 3 | Preserve it and report its ID and completed stage |
| Mutation sent but its outcome cannot be established | 4 | Report uncertainty; do not blindly repeat creation |

Human output is the default; JSON includes status, source ID, new ID when known,
completed stage, and an error when present. Do not claim a created ID after losing
the create response. A set difference is ambiguous when another client creates
concurrently. A move timeout may be reconciled by a read; do not retry it blindly.

Detached shell shortcuts discard output. Plan quiet success, a bounded durable
failure log under `$XDG_STATE_HOME/herdr-next-to-current/` (default
`~/.local/state/herdr-next-to-current/`), and best-effort Herdr notification with
the log location. Notification failure must not erase the original diagnostic.
These output and notification choices resolve previously open questions as
proposals; they are not recorded as previously accepted user decisions.

## Herdr integration

Use existing custom command bindings. Proposed creation is Alt+C and the move
popup is Alt+Shift+C; keep Alt+W's existing workspace picker. Disable the native
creation binding to avoid it taking precedence:

```toml
[keys]
new_workspace = []

[[keys.command]]
key = "alt+c"
type = "shell"
command = '"$HOME/.local/bin/herdr-next-to-current" workspace'
description = "new Space below current"

[[keys.command]]
key = "alt+shift+c"
type = "popup"
command = '"$HOME/.local/bin/herdr-next-to-current" reorder'
description = "move current Space before number"
width = "80%"
height = "80%"
```

The popup is a real terminal and receives input without adding a tab or split.
It receives `HERDR_ACTIVE_*` context; do not depend on `HERDR_PANE_ID` existing
inside it. [Custom command documentation](https://herdr.dev/docs/configuration/#custom-command-keybindings)
describes these launch modes and environment variables.

The existing `workspace-order` plugin supplies cursor movement and repeated
up/down reordering, followed by focus on Enter. Its
[documented interaction](https://github.com/pdjsh/herdr-plugins#workspace-order)
differs from this numeric source-to-anchor operation and omits adjacent creation.
An optional plugin manifest can package these same Python commands later, if
plugin discovery or distribution becomes useful.

## Implementation sequence and acceptance

1. **Context and transport.** Add bounded requests, strict context resolution,
   fake-server fixtures, and version checks. Prove named-session isolation,
   stale/moved-pane handling, and correct rejection without mutation.
2. **Creation.** Implement `workspace`, ID-anchored placement, configured/explicit
   cwd, focus control, lock behavior, and partial results. Cover middle/end/only
   workspace, grouped-source rejection, source deletion, move/focus failure,
   repeated triggers, and lost create responses without duplicate creation.
3. **Movement and TUI.** Implement `reorder`'s noninteractive forms, then the
   popup. Exercise moving up/down, first/last, self/already-adjacent, duplicate
   labels, more than nine rows, changed order while typing, target deletion,
   cancellation, resize, scrolling, and groups mixed with standalone workspaces.
   Verify source focus and pane/process identities survive movement.
4. **Disposable-session verification.** Run representative workflows against an
   isolated Herdr 0.9.3 session, with separate config/socket/state. Verify popup
   context, native cwd policy, actual sidebar order, focus behavior with two
   clients, and restoration of terminal settings on success/error/cancel.
   Never perform these experiments against the user's working session.
5. **Installation and dotfiles integration.** Run lint, package build, meaningful
   workflow tests, and an isolated tool install. Install from merged primary
   `main` with `just sync`; task worktrees use `uv run`. Prepare a separate
   chezmoi topic change for bindings, the existing my-git-utils-style bootstrap,
   and safe `daily-update` participation. Inspect source and deployed targets,
   validate the combined Herdr config, and test bootstrap/update skips.

Implement behavior tests with `unittest` and a fake socket server; no new runtime
dependency is required. Use small exhaustive order cases to catch both movement
directions and preservation of uninvolved rows. Use a PTY for terminal input,
resize, cancellation, and cleanup tests. Retain `just check` for lint/build and
add a test recipe when functional behavior exists.

Dotfiles integration must edit sources only:

| Chezmoi source | Absolute deployed target |
| --- | --- |
| `private_dot_config/herdr/config.toml` | `/home/vimkim/.config/herdr/config.toml` |
| `private_dot_config/my-scripts/bin/executable_daily-update` | `/home/vimkim/.config/my-scripts/bin/daily-update` |
| `.chezmoiscripts/run_once_after_install-herdr-next-to-current.sh` | Apply-time bootstrap script; no persistent target |

Bootstrap must preserve occupied/dirty checkouts and report retry guidance. A
run-once script that reports success after skipping an install will not retry
unchanged content automatically. Follow each repository's then-current Git and
deployment guidance: commit, obtain local integration approval, complete required
post-merge deployment, and clean up. A push or publication requires its own
explicit request. Verify shortcut delivery on the actual terminal; remotely
intercepted host shortcuts cannot be repaired by the helper.

## Next implementation request

Implement the two workspace workflows in this plan, keeping the existing command
and packaging. Start with context/transport and a fake-server workflow test, then
creation, noninteractive reorder, and the numeric popup. Preserve the existing
tab stub and unrelated changes. Treat group expansion as a separate decision if
requested. Validate live behavior only in a disposable session; prepare and
review dotfiles integration separately. Do not infer permission to mutate the
working Herdr session, deploy dotfiles, publish issues, or push from this design.
