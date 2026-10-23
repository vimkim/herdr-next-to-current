# Tab ordering evidence

Verified 2026-10-23 against the installed Herdr 0.9.3 schema, protocol 22,
release source at `7b116c05bfda646af39d2524c54e70c751f57ee8`, and a disposable server.
The user's active session was not used for runtime verification.

## Socket operations

| Method | Request | Successful result |
| --- | --- | --- |
| `tab.create` | `workspace_id`, optional `cwd` and `label`, `focus:false` | `tab_created` with `tab` and `root_pane` |
| `tab.list` | Explicit `workspace_id` | `tab_list` with ordered `tabs` |
| `tab.move` | `tab_id`, unsigned `insert_index` | `tab_list` with the workspace's authoritative order |
| `tab.focus` | `tab_id` | `tab_info` with `tab` |

`tab.create` appends. It has no insertion field or source-tab selector.
The installed CLI has no tab movement subcommand, but the socket method exists.
The helper sends all movement requests through its existing bounded socket client.
[Request types](https://github.com/herdrdev/herdr/blob/v0.9.3/src/api/schema/tabs.rs),
[handlers](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/tabs.rs).

`insert_index` is a zero-based slot in the list **before removal** of the moved tab.
The server subtracts one when the moved tab precedes the slot.
For `[NEW, A, B, C]`, moving NEW after B therefore requires slot 3.
For `[A, B, C, NEW]`, moving NEW after B requires slot 2.
The movement retains the active tab by its root-pane identity.
[Movement implementation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/workspace.rs#L591-L613).

The [upstream discussion](https://github.com/herdrdev/herdr/discussions/771)
reports the same insertion behavior. The release source independently confirms it.
Fake-server coverage exercises both movement directions.
The native test confirms real append-then-move placement and stable IDs.

## Directory and focus

When cwd is absent, `tab.create` calls Herdr's directory-policy resolver with the
captured workspace's backend focused-pane cwd. It does not accept a source tab.
The helper omits cwd to preserve that policy and passes an absolute cwd when requested.
The native test verifies follow, configured-path policy, and explicit override.
[Create handler](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/tabs.rs#L46-L131).

Creation with `focus:false` and movement preserve active selection.
Default helper behavior focuses the returned tab after verified placement.
The public focus request applies across attached clients.
`--no-focus` sends no focus request.
The native test verifies both modes with two attached PTY clients.
[Focus handler](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/api/tabs.rs#L133-L141),
[focus projection](https://github.com/herdrdev/herdr/blob/v0.9.3/src/server/headless/client_views.rs).

## Concurrency and identity

The helper captures the source before creation and revalidates membership after creation.
Every tab list uses the captured workspace. Labels and display numbers are not identities.
A moved pane resolves through one `pane.current` call, which supplies both canonical IDs.
The existing per-socket lock serializes helper mutations, including Space operations.
Other clients can still change order between requests.

Movement uses one numerical insertion request, followed by returned-order and fresh-order checks.
A competing change can invalidate that request. The helper reports this and preserves the new tab.
It does not repeatedly move against another client.
A lost create response remains uncertain. A lost move or focus response can succeed
only when a fresh read confirms its result. No mutation is retried.
