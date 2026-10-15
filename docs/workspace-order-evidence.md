# Workspace ordering evidence

Verified 2026-10-15 through read-only local commands and release source. Installed CLI: Herdr 0.9.3; bundled API schema: protocol 22; live `herdr api snapshot`: server 0.9.3/protocol 22. The release tag resolves to commit `7b116c05bfda646af39d2524c54e70c751f57ee8`. Source was inspected using `git show v0.9.3:<path>` in `/home/vimkim/temp/herdr-source-v0.9.1`; its checkout directory name does not identify the inspected revision. No runtime state, packages, or configuration were changed.

## Available operations

Herdr already exposes both movement methods, although its 0.9.3 workspace CLI has no move subcommand. The installed `herdr api schema --json` confirms these request fields:

| Method | Parameters needed here |
| --- | --- |
| `workspace.create` | Optional `source_workspace_id`, `cwd`, `label`; `focus` defaults to false |
| `workspace.move` | `workspace_id`, unsigned `insert_index` |
| `workspace.move_block` | Ordered `workspace_ids`, optional `before_workspace_id` |

The CLI does not expose `source_workspace_id`, either. A Python helper can therefore use the public socket API directly for both features. [Request types](https://github.com/herdrdev/herdr/blob/v0.9.3/src/api/schema/workspaces.rs#L7-L46), [CLI dispatch and creation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/cli/workspace.rs#L7-L102).

`workspace.move` takes a zero-based insertion slot in the list **before removal**. Moving an earlier item toward the end subtracts one internally. `workspace.move_block` instead removes the supplied IDs and inserts them, in supplied order, before a stable workspace ID; omitting the anchor appends. Both preserve logical active/selected workspace identities. Prefer a one-ID block for numeric insertion: map the displayed number to its workspace ID and send that ID as the anchor. [Movement implementation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/actions.rs#L475-L570).

The block handler validates every source and anchor before mutation, rejects duplicate/empty sources and an anchor inside the block, and returns the authoritative ordered workspace list. Successful changes emit `workspace_reordered`; no-ops emit nothing. It applies no worktree-group constraints. [Block handler](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/workspaces.rs#L171-L238).

## Creation, directory, and focus

Creation appends a normal workspace, returns `result.workspace`, `result.tab`, and `result.root_pane`, and saves session state. With an existing active workspace, `focus:false` keeps selection there; an empty session necessarily selects its first workspace. Thus adjacent creation requires separate create, move, and optionally focus requests; they are not one transaction. [Creation implementation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/creation.rs#L126-L160), [creation result](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/creation.rs#L275-L283).

`source_workspace_id` selects the workspace used by Herdr's configured new-terminal directory policy when `cwd` is omitted. An explicit `cwd` overrides that behavior and skips source-workspace validation, so the helper must independently validate placement context even when passing a directory. [Create handler](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/workspaces.rs#L39-L84).

This fixes directory selection from the wrong **workspace**, but does not select a captured source tab or pane. The source workspace's backend active tab and focused pane provide the follow directory; runtime follow detection may differ from shell/reported cwd. Policies include follow, home, server current directory, and a configured path. Passing a captured absolute cwd guarantees that directory, while omitting it preserves Herdr's policy. These are distinct contracts. [Directory resolution](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/creation.rs#L10-L100).

Public focus projects across attached clients. A helper cannot promise invoking-client-only focus through `workspace.focus`; retaining a `--no-focus` option is appropriate. [Session-wide focus handling](https://github.com/herdrdev/herdr/blob/v0.9.3/src/server/headless/client_views.rs#L809-L847).

## Sidebar groups and numbers

Raw workspace order differs from sidebar projection when Herdr worktree groups exist. The sidebar groups records by repository key when at least two members include a non-linked parent; it emits that parent before children even when raw records are interleaved. Collapse state also changes visible rows. API records expose `worktree.repo_key` and `is_linked_worktree`, but not client-specific collapse state. [Sidebar projection](https://github.com/herdrdev/herdr/blob/v0.9.3/src/client/shell/sidebar.rs#L458-L544), [public workspace records](https://github.com/herdrdev/herdr/blob/v0.9.3/src/api/schema/workspaces.rs#L61-L85).

Native dragging rejects linked-child sources and moves a parent with same-key members as a block. Raw movement has no equivalent guard. Ordinary creation constructs a normal workspace; a matching cwd does not make it a managed linked-worktree child. Therefore literal sidebar adjacency and preserving groups require an explicit policy. Existing ADR 0002 rejects grouped creation sources. Numeric movement should not silently bypass that boundary: grouped sources or anchors need rejection or a separately agreed group-aware contract. TUI indices must describe its own displayed rows, not claim to reproduce client-specific collapsed sidebar numbers. [Native dragging](https://github.com/herdrdev/herdr/blob/v0.9.3/src/client/shell/mouse.rs#L566-L645), [normal workspace constructor](https://github.com/herdrdev/herdr/blob/v0.9.3/src/workspace.rs#L399-L414).

## Launch surface and context

A custom `type="popup"` command provides a terminal UI without adding a pane; the process receives input including Escape and closes on exit. `type="shell"` is detached and suitable for creation. Custom commands receive the socket, binary, and available `HERDR_ACTIVE_WORKSPACE_ID`, `HERDR_ACTIVE_TAB_ID`, `HERDR_ACTIVE_PANE_ID`, and `HERDR_ACTIVE_PANE_CWD` at launch. Capture those once; do not later replace the source with global focus. Shell bindings discard standard streams, and detached exit codes are discarded, so errors need a persistent record and best-effort notification. [Custom command implementation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/custom_commands.rs#L212-L304), [child reaping](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/runtime.rs#L9-L27), [popup behavior](https://herdr.dev/docs/configuration/#custom-command-keybindings).

This research process's inherited `HERDR_WORKSPACE_ID` is absent from the live snapshot. That is evidence to reject stale caller context, not permission to adopt the server's focused workspace. Direct-pane invocation must resolve a pane identity rather than trust launch-time parent IDs; Herdr supports moved-pane aliases through `pane.current`. [Pane resolution](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/panes.rs#L144-L157), [alias lookup](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/ids.rs#L106-L108).

Plugins can call the same public API. A manifest popup supplies `HERDR_PLUGIN_CONTEXT_JSON` for the underlying workspace/pane, has no `HERDR_PANE_ID`, and remains a singleton modal. A small optional manifest can package the same Python commands; plugin ownership does not require Rust. [Plugin popup implementation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/plugins/panes.rs#L11-L50), [captured plugin context](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/plugins/panes.rs#L237-L274).

Current source and deployed config bind native creation to Alt+C and contain no Alt+Shift+C binding. Set `new_workspace=[]` (or an empty string) before installing a custom Alt+C binding: native actions take precedence over custom commands. Removing the setting restores the default Prefix+Shift+N. Alt+Shift+C is available in inspected user/default bindings for the popup. [Binding representation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/config/keybinds.rs#L45-L83), [default](https://github.com/herdrdev/herdr/blob/v0.9.3/src/config/model.rs#L1123), [dispatch order](https://github.com/herdrdev/herdr/blob/v0.9.3/src/input/keybindings.rs#L223-L231).

## Transport and existing plugin

Ordinary socket calls use one newline-delimited JSON request/response per connection. Request IDs correlate responses; no create deduplication is provided. A lost create response leaves an uncertain outcome: do not retry creation or identify its result by an ambiguous list difference. [Socket dispatcher](https://github.com/herdrdev/herdr/blob/v0.9.3/src/api/server.rs#L296-L484).

`pdjsh/herdr-plugins` already includes a Rust `workspace-order` popup. At inspected commit `b7376e5a0edb2f4080ad1220bade539efdee6e01`, j/k selects, J/K moves the selected workspace one step, and Enter focuses it. It does not implement pinned-caller numeric insert-before or adjacent creation. Its terminal rows show labels/IDs rather than typed destination numbers. Adapting it is possible, but a Python helper can match the requested interaction with less build machinery. [Plugin implementation](https://github.com/pdjsh/herdr-plugins/blob/b7376e5a0edb2f4080ad1220bade539efdee6e01/plugins/workspace-order/src/main.rs#L120-L179), [popup manifest](https://github.com/pdjsh/herdr-plugins/blob/b7376e5a0edb2f4080ad1220bade539efdee6e01/plugins/workspace-order/herdr-plugin.toml).
