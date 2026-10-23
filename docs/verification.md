# Implementation verification and local rollout

Tab milestone verified 2026-10-23. Earlier Space milestone verified 2026-10-15.
Implementation contract: [PLAN.md](../PLAN.md).
Herdr wire shapes and group projection are pinned to the
[0.9.3 source evidence](workspace-order-evidence.md); the running disposable server
also reports version 0.9.3 and protocol 22.

## Adjacent tab checks, 2026-10-23

- `just check` passes: Ruff lint and format checks, 76 behavior tests pass,
  one opt-in native test skips, and wheel/source distributions build.
- Twenty-four tab tests use the real CLI and fake Unix socket, or the public
  workflow interface for captured-context and lock checks. They cover middle,
  final, and only-tab sources, both focus modes, labels, cwd, custom commands,
  explicit selectors, moved/stale panes, missing/conflicting context, unsupported
  servers, and malformed responses. They also cover contention, bounded locking,
  partial failures, lost create/move/focus responses, and failed reconciliation.
  Known created tabs survive failures. Lost creation never infers an ID or retries.
- `HERDR_LIVE_TEST=1 uv run python -m unittest tests.test_live -v` passes on
  Herdr 0.9.3/protocol 22 with two disposable PTY clients. It verifies middle,
  final, and only-tab placement, default focus, `--no-focus`, label, follow cwd,
  configured directory policy, and explicit cwd. Existing pane/terminal/tab IDs
  and each pre-existing pane's shell PID survive placement.
- The native test disables native tab creation and sends actual Alt+T bytes from
  a middle tab. It verifies the custom command's captured workspace/tab IDs,
  adjacent placement, and focus. Existing Alt+C and Alt+Shift+C checks also pass.
- The tab implementation was checked on Python 3.14.0. Earlier interpreter
  evidence below applies to the previous Space milestone.
- A regular `uv tool install` of the built wheel into temporary tool/bin
  directories passes help and the installed console's explicit-context tab
  creation, adjacency, label, and default-focus checks against the fake socket.
  The normal installed command remains unchanged pending integration.

The separately prepared dotfiles change is on `feat/herdr-adjacent-tabs` in
`/home/vimkim/.local/share/chezmoi-herdr-adjacent-tabs`, based on `main` at `71961e8`.
It changes only `private_dot_config/herdr/config.toml`, whose target is
`/home/vimkim/.config/herdr/config.toml`. It sets `new_tab=[]` and binds Alt+T to
`"$HOME/.local/bin/herdr-next-to-current" tab --quiet`.

`herdr config check` accepts the proposed source. TOML parsing and a complete
comparison against the starting configuration confirm that all other settings
and bindings remain identical. The source-to-target chezmoi diff contains only
those changes. The focused dotfiles Herdr suite passes 56 tests with two opt-in
native tests skipped. No working-session configuration was deployed or reloaded.

Merge approval remains required. After approved helper integration, install from
the canonical `main` checkout with `just sync` and verify the installed command.
Enable the binding only after that verification. Dotfiles merge approval authorizes
its documented `chezmoi-apply-unmodified` deployment. Main merge approval also
authorizes the configured-remote main push under the current global Git guidance.
Actual host-terminal shortcut interception still requires a check in the user's client.

## Space checks, 2026-10-15

- `just check`: Ruff lint/format, 53 passing standard-library behavior tests
  (the opt-in live test is skipped), wheel and source distribution builds.
- Fake Unix socket tests cover strict context, named socket isolation, moved and
  stale panes, source deletion/regrouping, partial creation, lost create/move/focus
  responses, malformed/oversized responses, absolute request deadlines, bounded
  lock waits, concurrent creates, and notification/log failures.
- Small exhaustive cases cover every source/anchor for list sizes 1–5 and all
  raw permutations of two standalone Spaces beside a two-member worktree group.
  Both raw order and expanded sidebar projection are verified.
- PTY tests exercise real curses input, resize, success, cancellation, and error
  cleanup; terminal attributes match their original values after exit. Picker
  tests also cover multi-digit numbers, Backspace, negative/empty/invalid input,
  scrolling, group explanations, refresh, and changed number-to-ID mappings.
- `HERDR_LIVE_TEST=1 uv run python -m unittest tests.test_live -v` passes against a
  newly started server with two real terminal clients. It verifies adjacent
  creation, source `follow` cwd, configured path policy, explicit cwd override,
  both focus modes, reorder, and surviving pane/terminal/tab IDs and shell PIDs.
  Actual Alt+C and Alt+Shift+C byte sequences trigger the shell binding and popup;
  popup environment confirms its captured Space and socket. Enter moves that
  Space before row 1 without requesting focus.
- An isolated `uv tool install` of the built wheel passes `--help` and installed
  console creation/reorder workflows against the fake socket. The normal
  installed command is unchanged until the approved main integration.
- The complete suite passes on Python 3.12.9 and 3.14.0. All runtime modules also
  parse with Python 3.11 grammar. A Python 3.11 interpreter download did not
  complete and was stopped, so actual 3.11 runtime execution remains unverified.

The live test owns temporary configuration, session/state/cache directories,
sockets, shells, and clients. It stops only its own server and removes its
artifacts. It never uses the invoking shell's inherited Herdr socket or session.
Live grouped-worktree rendering was not exercised; projection and group policy
have exhaustive fake-server coverage. Actual user terminal or host shortcut
interception remains a manual delivery check after deployment.

## Earlier Space integration, 2026-10-15

Topic: `feat/herdr-space-workflows` in
`/home/vimkim/.local/share/chezmoi-herdr-space-workflows`, commit `208935c`, based on dotfiles `main`.

| Source | Absolute deployed target |
| --- | --- |
| `private_dot_config/herdr/config.toml` | `/home/vimkim/.config/herdr/config.toml` |
| `private_dot_config/my-scripts/bin/executable_daily-update` | `/home/vimkim/.config/my-scripts/bin/daily-update` |
| `.chezmoiscripts/run_once_after_install-herdr-next-to-current.sh` | Apply-time script; no persistent target |

Config changes disable native workspace creation, bind Alt+C to quiet adjacent
creation, and bind Alt+Shift+C to the 80% numeric popup. Existing Alt+W, workspace
movement commands, and tab bindings are preserved. Source and deployed targets
were inspected; `chezmoi --source <task-checkout> diff -- <target>` shows only the
expected config and daily-update changes. Combined TOML parses successfully.

Bootstrap clones a missing checkout and installs only clean independent primary
`main` with the expected GitHub origin. Occupied paths, linked worktrees, detached
or topic branches, dirty trees, missing prerequisites, and installation errors
are preserved and return a nonzero status with retry guidance. Real disposable
chezmoi applies prove failed run-once scripts retry and successful ones are not
run again unchanged.

Daily-update uses the existing fetch / fast-forward / sync workflow. The Herdr
checkout additionally requires primary `main` tracking `origin/main` and the
expected GitHub origin. Dirty, linked, wrong-origin, missing, ahead, or diverged
checkouts are skipped. Tests use real disposable Git repositories and local
remotes; no real updates or tool installs occur.

Dotfiles checks: 19 daily-update tests, 6 bootstrap tests (including real chezmoi
retry state), 38 existing Herdr helper tests, Bash syntax, ShellCheck, and config
preservation assertions pass. The full unrelated dotfiles test corpus was not run.

## Historical Space rollout procedure, 2026-10-15

1. Verify clean primary destinations on `main`, rebase and integrate the helper
   topic, run proportionate checks, then run `just sync` from
   `/home/vimkim/gh/herdr-next-to-current`. Verify the installed command.
2. Rebase and integrate the separate dotfiles topic. Per dotfiles `AGENTS.md`, run
   `chezmoi-apply-unmodified` once across managed files and symlinks, preserve and
   report locally modified skips, then verify the two affected targets with
   `chezmoi diff`. The helper excludes run scripts; the equivalent local install
   is already complete through `just sync`. Bootstrap execution is available via
   a deliberate future chezmoi apply.
3. Check actual terminal shortcut delivery and reload configuration through the
   user's normal Herdr procedure. Do not use working-session mutations as tests.
4. Remove only these merged task worktrees and branches after confirming their
   commits or squash changes are included and preserving any valuable artifacts.

This earlier milestone used a separate publication approval. The current global
Git guidance authorizes a main push after an approved main merge.
No remote branch, issue, or PR changed during the tab implementation before approval.
