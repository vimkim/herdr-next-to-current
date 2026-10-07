# herdr-next-to-current project plan

Updated: 2026-10-07. Initial stage: establish the uv package, command interface, repository, and implementation plan. Terminal mutation and chezmoi integration are separate implementation milestones.

## Accepted direction

| Item | Direction |
| --- | --- |
| Project and distribution | `herdr-next-to-current` |
| Console command | `herdr-next-to-current` |
| Python package | `herdr_next_to_current` |
| Canonical checkout | `~/gh/herdr-next-to-current` |
| GitHub repository | `https://github.com/vimkim/herdr-next-to-current` |
| Packaging | Standalone Python uv project, installed as an editable uv tool |
| User interface | `herdr-next-to-current workspace ...` and `herdr-next-to-current tab ...` |
| Bootstrap | Automatically install with the chezmoi apply phase on a fresh machine, matching my-git-utils |
| Maintenance | Participate in `daily-update` as a personal tool checkout |
| Initial runtime | Linux, including WSL and the remote Rocky Linux server |

This is a helper launched by Herdr custom command bindings or from a Herdr pane. A native Herdr plugin manifest is optional future integration; the requested Python binary does not require plugin registration.

## Current evidence

Herdr's current tab and workspace creation schemas have no ordering parameter. New tabs append in [the released tab implementation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/workspace.rs#L571), and ordinary workspaces append in [the released workspace implementation](https://github.com/herdrdev/herdr/blob/v0.9.3/src/app/creation.rs#L148). Its [socket API](https://herdr.dev/docs/socket-api/#raw-methods) provides `tab.move`, `workspace.move`, and `workspace.move_block`.

The installed Herdr 0.9.1 already supplies the create/move request schemas. This means the helper can use the installed server without an upgrade. Validate the server's schema and responses at implementation time; this is evidence of available operations, not proof that the new helper works.

The user's existing `herdr-move-workspace` helper reads the invoking command's socket and workspace ID, reads a snapshot, and moves the workspace by insertion index. Reuse that experience in one shared client rather than distributing another personal script through dotfiles.

## Proposed CLI contract

```text
herdr-next-to-current --help
herdr-next-to-current --version
herdr-next-to-current workspace [--label TEXT] [--cwd PATH] [--no-focus]
herdr-next-to-current tab [--label TEXT] [--cwd PATH] [--no-focus]
```

The two resource commands create immediately after the source item by default. They do not require a separate `create` verb. Creation focuses the new item by default; `--no-focus` retains the previous view. Explicit source or socket selectors, output format, and optional move commands remain design decisions for the interview.

The scaffold recognizes this interface but returns an explicit nonzero error for creation. It must never silently succeed while performing no operation.

## Desired behavior

```text
Before:  A, B(current), C, D
Create:  A, B, C, D, NEW
Move:    A, B, NEW, C, D
Focus:         NEW(current)
```

The same ordering applies to tabs in a workspace and ordinary workspaces on one server. Creating after the last item leaves the new item at the end. IDs determine the anchor; labels and display numbers do not.

1. Capture the triggering context and socket before creation. For custom commands, use the provided `HERDR_ACTIVE_WORKSPACE_ID` / `HERDR_ACTIVE_TAB_ID`. For direct invocation, resolve the calling pane's identity and source. Do not replace known source IDs with another client's global focus.
2. Confirm the source exists and read its ordered peers. Keep tabs scoped to the correct workspace and all calls scoped to the same server.
3. Create with `focus: false`, carrying an explicit cwd and label when supplied. Preserve Herdr's directory policy when cwd is omitted; confirm it follows the intended source with multiple clients.
4. Keep the successful create response's new ID. A lost create response must not trigger a blind retry, since the item might already exist.
5. Read the order again, find the original source by ID, and move the new item with `insert_index = source_index + 1`. Skip a redundant move when it is already adjacent.
6. Verify adjacency. Correct an intervening reorder at most once; report continued contention rather than looping indefinitely.
7. Focus the new ID unless `--no-focus` was requested, and verify which attached clients the focus API affects.

Use bounded socket I/O, newline-delimited JSON, matching request IDs, and structured error handling. A per-socket helper lock can serialize this tool's own invocations. It cannot lock unrelated clients. Creation and movement remain separate operations; atomic placement would need native Herdr support.

Preserve a created item if a later move or focus fails. Report its ID and completed stage so the user can recover without losing a running shell.

## Package and module design

Follow the my-git-utils convention: one distribution, a `src/` package, a tracked `uv.lock`, and a small `justfile`.

```text
pyproject.toml
uv.lock
justfile
README.md
PLAN.md
src/herdr_next_to_current/
  __init__.py
  cli.py          # user arguments, context, output, exit status
  client.py       # Herdr socket transport and request/response validation
  placement.py    # source lookup, creation, movement, verification, focus
tests/
  test_workflow.py # fake socket server; full user-visible workflows
docs/
  agents/         # issue tracker and domain setup after the setup skill
  adr/            # settled decisions after the design interview
GLOSSARY.md       # vocabulary established during the interview
```

Only packaging and the command skeleton belong to the initial scaffold. Add pytest and behavior tests with the first functional slice. Use `just lint` and `just build` now; add `just test` when executable behavior is introduced.

`just sync` installs the primary `main` checkout with `uv tool install --editable . --reinstall`. Do not install from a task worktree: removing it would break the editable command. Document development-time execution through `uv run` instead.

## Chezmoi bootstrap and daily-update integration

The existing reference in `vimkim/dotfiles` is `.chezmoiscripts/run_once_after_install-my-git-utils.sh`. It clones the missing repository into `~/gh/my-git-utils`, checks `uv` and `just`, and runs `just sync`. The managed `daily-update` script later refreshes the checkout and reinstalls the tools.

Mirror that model when the helper is ready:

1. Add `.chezmoiscripts/run_once_after_install-herdr-next-to-current.sh` to the **chezmoi source repository**, in its own topic worktree.
2. Clone `https://github.com/vimkim/herdr-next-to-current.git` into `~/gh/herdr-next-to-current` only when no checkout exists. Never replace an occupied unrelated directory or discard local work.
3. Require `git`, `uv`, and `just`; run `just --justfile "$dir/justfile" --working-directory "$dir" sync`. Use the same nonfatal bootstrap and explicit retry guidance as my-git-utils.
4. Add `herdr-next-to-current` to `PERSONAL_TOOLS` in the chezmoi source `private_dot_config/my-scripts/bin/executable_daily-update`. Its exact deployed target is `~/.config/my-scripts/bin/daily-update`.
5. Preserve existing daily-update rules: skip dirty/ahead/diverged/missing/untracked checkouts, fast-forward only, and refresh an independent tool even when another step fails.
6. Update the dotfiles bootstrap documentation and focused daily-update tests. Test the run-once bootstrap in a temporary home with stubbed external commands.
7. Inspect the rendered changes and obtain the user's normal local merge review. Publishing `vimkim/dotfiles` and deploying any existing-machine target each require their own explicit request.

The automatic-install trigger is **`chezmoi init --apply`**, because scripts run during apply. Plain `chezmoi init` obtains source state and does not install this binary. Chezmoi's [script lifecycle](https://www.chezmoi.io/user-guide/use-scripts-to-perform-actions/) documents the run-once and after-apply naming rules.

Run-once scripts also run on a later apply when newly introduced, not exclusively on init. Keep the script idempotent for an existing machine. Do not invoke a broad chezmoi apply while developing this integration.

## Herdr shortcuts and Windows Terminal

Retain the agreed navigation layout: Alt+Left/Right for tabs and Alt+Up/Down for workspaces; add Shift to reorder. Ctrl+A followed by Up/Down is a proposed fallback. The latest chezmoi source checked during scaffolding has workspace movement aliases but does not contain those prefix fallbacks or native tab movement bindings; verify the current source before changing them.

Once adjacent creation works, route Alt+T to `herdr-next-to-current tab` and Alt+C to `herdr-next-to-current workspace` through detached Herdr custom commands. Resolve native/custom binding conflicts before enabling them. Do not change the live creation bindings as part of the initial scaffold.

All Herdr configuration edits must go through the **chezmoi source**, in a sibling topic worktree. The source file is `private_dot_config/herdr/config.toml`; its deployed target is `~/.config/herdr/config.toml`. Inspect the rendered diff for that exact target, obtain the required review, and apply only that target when deployment is requested. Never edit the deployed config directly. The current source and deployed config were verified to match during scaffolding; preserve later user changes.

Windows Terminal's default pane shortcuts overlap with all eight modified arrows. Its [pane documentation](https://learn.microsoft.com/en-us/windows/terminal/panes) explains the defaults. Free those keys locally in Windows Terminal; a remote helper cannot recover keys intercepted before WSL or SSH.

## Remaining design decisions

These are the frontier for `grill-with-docs`; facts should be investigated by the agent and policy choices settled with the user.

- What explicit source/socket selectors should the CLI expose, and how should ambiguous context fail?
- Does first-release workspace support include grouped Git worktrees? Literal visual adjacency may conflict with preserving the existing group structure.
- What cwd and focus guarantees are possible when clients view different tabs or workspaces?
- What should rapid repeated creation do: always use the captured source, or intentionally build a chain?
- Should manual tab/workspace movement become resource subcommands, or stay in the existing Herdr bindings and mover?
- What output and exit-code contract should distinguish success from a preserved, partially completed creation?
- Is a native Herdr plugin manifest valuable after the standalone command and custom bindings work?

## Delivery sequence

1. **Project starting point:** uv package, the correctly named console entry point, proposed help interface, build/lint checks, revised plan, and GitHub publication.
2. **Agent-flow setup:** use `setup-matt-pocock-skills` to settle issue tracker and steering-file choices and establish domain-document conventions. A GitHub tracker is a reasonable recommendation for this repository; the setup skill asks before selecting it.
3. **Design interview:** use `grill-with-docs` to settle the frontier and retain vocabulary and ADRs. Use a disposable-session prototype only where a runnable check is necessary to establish Herdr behavior.
4. **Executable specification:** turn the agreed design into acceptance criteria. If it spans sessions, use `to-spec` then `to-tickets`; otherwise proceed to `implement` with the agreed plan.
5. **Functional slices:** implement transport/context, adjacent tab creation, then ordinary workspace creation. Drive meaningful end-to-end tests with a fake socket server and verify actual API behavior in a disposable Herdr session.
6. **Integration:** install from merged main, prepare the chezmoi bootstrap and daily-update change, and add Herdr custom creation shortcuts after focused checks.
7. **Review and publish:** commit task changes, run Standards and Spec review for the functional implementation, obtain local rebase/fast-forward merge confirmation, then push explicitly authorized repositories. Run `retro` after the build.

## Acceptance checks for the working release

| Check | Required outcome |
| --- | --- |
| uv build and isolated tool install | Command is exactly `herdr-next-to-current`; import package is correct |
| Tab creation in the middle and at the end | New ID immediately follows source; all other IDs retain relative order |
| Ordinary workspace creation | Same placement semantics on the intended server |
| Invocation context differs from global focus | Captured source determines placement |
| Multiple named sessions and SSH | No silent fallback to another socket or machine |
| Focus enabled and `--no-focus` | Documented client focus behavior holds |
| Label, explicit cwd, omitted cwd | Values and configured source policy behave as documented |
| Move/focus failure after creation | Created process survives; new ID and completed stage are reported |
| Lost create response | No automatic second creation |
| Concurrent helper calls and unrelated reorder | Own calls serialize; continued contention produces a bounded failure |
| Git worktree group | Agreed group policy is enforced before unsupported mutation |
| Fresh chezmoi init with apply | Checkout is cloned and console command is installed |
| Existing checkout and missing prerequisites | Local work survives; diagnostics include a retry command |
| Daily-update | Same safety/skip rules and editable reinstall as my-git-utils |

## Next prompt

Open the canonical project checkout and use:

```text
$setup-matt-pocock-skills

Set up this repository for the engineering flow. Recommend GitHub Issues,
single-context GLOSSARY.md and docs/adr, and the same lightweight conventions
as ~/gh/my-git-utils. Resolve the setup skill's choices before writing them.

Then use $grill-with-docs on PLAN.md for herdr-next-to-current. Settle source
context, grouped workspaces, cwd, multi-client focus, partial failures, CLI
output, and chezmoi bootstrap/daily-update behavior. Keep the binary name
herdr-next-to-current and the workspace/tab resource interface. Investigate
facts yourself, ask me only decisions that change the design, and retain the
agreed vocabulary and decisions. End with the next implementation prompt;
do not start the functional build during the interview.
```

This follows the ask-matt route provided in the session: setup first, then the stateful interview for a project with a working directory. The user has not yet invoked that engineering interview; the initial scaffold is its input.
