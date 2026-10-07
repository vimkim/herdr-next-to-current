# Session handoff

Prepared 2026-10-07 for a fresh agent continuing this project. The user explicitly
requested this document inside the project directory, overriding the handoff
skill's usual temporary-directory destination.

## Start here

The canonical checkout is `/home/vimkim/gh/herdr-next-to-current`; the public
repository is [vimkim/herdr-next-to-current](https://github.com/vimkim/herdr-next-to-current).
Read [README.md](README.md) for the implemented scaffold and [PLAN.md](PLAN.md)
for the accepted direction, remaining design decisions, acceptance checks, and
next prompt. Those documents contain the design; this handoff records session
state and constraints instead of repeating them.

The intended next session is project-flow setup followed by the design
interview, ending with an implementation prompt. The user has not invoked that
interview or authorized the functional build yet. Their last implementation
scope choice was **publish scaffold and plan first**. This handoff request does
not expand that scope.

## Completed work and verification

- Scaffold commit `d1fe92bfe44b01c96b7d3823f83ac7a199bf506f` was published to remote
  `main`, then rebased and fast-forward merged into local `main` with the user's
  explicit approval. Its topic worktree and branch were removed.
- Before this handoff, canonical `main` was clean, tracked `origin/main`, and
  contained that same commit. Inspect current status before continuing; other
  sessions can change the repositories.
- `just check` passed (Ruff lint/format and uv sdist/wheel builds). An isolated uv
  tool installation verified the exact executable name and help/version output.
  Both creation commands deliberately returned exit code 2 with the scaffold
  error. No terminal mutation was exercised or claimed.
- Functional creation, automatic installation, daily-update integration, and
  helper-backed Herdr bindings remain planned. No global editable installation
  or dotfiles changes were made during scaffolding.
- Work-tracker items 282 (Herdr research) and 287 (project scaffold/publication)
  are complete. Register new work only when the global tracking criteria apply.

This handoff itself is prepared on `docs/session-handoff` in sibling worktree
`/home/vimkim/gh/herdr-next-to-current-handoff`. It requires the normal local
merge confirmation. If that branch still exists, inspect its state and finish
the review/merge workflow before starting another repository-changing task.
Publishing this new document has not been requested.

## User constraints and environment

- Preserve the binary name and resource interface already recorded in PLAN.md.
  The repository is intentionally public, like the reference my-git-utils tool.
- **Never edit `~/.config/herdr/config.toml` directly.** Make changes to the
  chezmoi source `private_dot_config/herdr/config.toml` in a topic worktree of
  `/home/vimkim/.local/share/chezmoi`. Publishing dotfiles and deploying exact
  targets each need an explicit request. Avoid a broad chezmoi apply.
- Follow the supplied global AGENTS.md workflow: sibling task worktrees from
  main, preserve unrelated changes, commit completed task work, then ask once
  for local rebase and fast-forward merge. Clean up only the merged task branch
  and worktree. Push and deployment are separately authorized actions; prior
  scaffold publication is not blanket authorization for future pushes.
- This is remote Rocky Linux 9 reached through Windows 11 Windows Terminal,
  Ubuntu WSL, and SSH. X11 forwarding makes GUI programs impractical; never
  launch a browser or GUI. Use terminal tools or provide URLs for local opening.
- Windows Terminal can intercept modified arrows before they reach SSH. Local
  keyboard delivery remains unverified; a remote helper cannot repair it.
- Shortcut state changed between sessions. Inspect the current chezmoi source;
  do not restore earlier snippets as though they were authoritative. At the
  scaffold check, source and deployed config matched, while earlier prefix
  fallbacks and native tab movement bindings were absent.
- Use `uv run` in task worktrees. `just sync` intentionally permits editable
  installation only from the primary main checkout, so cleanup cannot break it.

## Supporting artifacts

These are existing references, not additional work to repeat:

- [PLAN.md](PLAN.md#next-prompt): the ready-to-use setup/interview prompt and
  links to primary Herdr evidence. Revalidate API facts at implementation time;
  availability of create/move methods does not establish correct helper behavior.
- `/home/vimkim/temp/herdr-next-to-current/findings.md`: original cited Herdr
  documentation/source investigation.
- `/home/vimkim/temp/herdr-next-to-current/WINDOWS-TERMINAL.md` and
  `windows-terminal-unbind.json` in that directory: Windows Terminal guidance.
  Historical `shortcuts.toml` and PLAN.md there are superseded by the current
  source and the project plan.
- `/home/vimkim/gh/my-git-utils`: packaging, editable install, and agent-flow
  reference. Preserve its unrelated local commits and changes.
- In `/home/vimkim/.local/share/chezmoi`, consult
  `.chezmoiscripts/run_once_after_install-my-git-utils.sh`,
  `private_dot_config/my-scripts/bin/executable_daily-update`,
  `docs/daily-update.md`, and `tests/test_daily_update.py` for integration.

## Suggested skills

Call the Skill tool for these installed skills when continuing the corresponding
phase; if this harness has no Skill tool, read the exact SKILL.md instead.

1. `setup-matt-pocock-skills` —
   `/home/vimkim/.agents/skills/setup-matt-pocock-skills/SKILL.md`.
   This has not run. Follow its required choices and draft review before writing.
   GitHub Issues and a single glossary/ADR context are recommendations, not
   recorded user decisions. Neither AGENTS.md nor CLAUDE.md existed in the
   scaffold, so the steering-file choice still needs resolution.
2. `grill-with-docs` —
   `/home/vimkim/.agents/skills/grill-with-docs/SKILL.md`.
   After setup, interview against PLAN.md; it invokes `grilling` and
   `domain-modeling` to retain vocabulary and decisions. Investigate facts
   independently and ask only decisions that materially change the design.
3. `writing-for-agents` when creating steering files; `prototype` only if an
   unresolved design question needs a disposable runnable experiment.
4. Later, after implementation is requested: route through `ask-matt` for
   `to-spec`/`to-tickets` if needed, then the implementation/TDD flow and
   `code-review`. Use `track-work` for work spanning sessions or meeting the
   global duration/parallel-work criteria. Do not start these phases just to
   consume this handoff.

The first actionable continuation is the prompt already in
[PLAN.md](PLAN.md#next-prompt), once the user asks to begin that phase.
