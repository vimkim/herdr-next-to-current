# Implementation verification and local rollout

Verified 2026-10-15. Implementation contract: [PLAN.md](../PLAN.md).
Herdr wire shapes and group projection are pinned to the
[0.9.3 source evidence](workspace-order-evidence.md); the running disposable server
also reports version 0.9.3 and protocol 22.

## Checks

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

## Separate chezmoi topic

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

## Rollout after local integration approval

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

Pushes remain separate. Until publication is explicitly requested, fresh machines
clone the existing remote revision, which may still be the earlier scaffold.
No remote branch, issue, or PR was changed by this implementation task.
