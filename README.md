# herdr-next-to-current

A standalone Python uv tool planned for opening a Herdr Space immediately below the current Space and moving the current Space before a numbered destination. Herdr's API calls these `workspaces`.

**Status: initial scaffold.** The installed command provides `--help`, `--version`, and the proposed `workspace` / `tab` interface. Creation currently exits with an explicit error and makes no Herdr changes. The numbered `reorder` TUI is planned. The implementation and chezmoi integration are described in [PLAN.md](PLAN.md).

## Intended commands

```sh
herdr-next-to-current workspace --label review
herdr-next-to-current workspace --cwd ~/project --no-focus
herdr-next-to-current reorder
```

Creation captures the invoking workspace, creates below it, verifies the order, and focuses the new workspace unless `--no-focus` was requested. The reorder popup lists numbered workspaces; entering a number moves the invoking workspace before that row while preserving focus. Both workflows use Herdr's socket interface. Adjacent tab creation remains a later milestone.

## Installation

Requires Python 3.11 or later, [uv](https://docs.astral.sh/uv/), and [just](https://just.systems/). Herdr is required for the planned terminal operations.

```sh
git clone https://github.com/vimkim/herdr-next-to-current.git ~/gh/herdr-next-to-current
cd ~/gh/herdr-next-to-current
just sync
herdr-next-to-current --help
```

`just sync` uses `uv tool install --editable . --reinstall`, matching [my-git-utils](https://github.com/vimkim/my-git-utils). The console entry point is named **`herdr-next-to-current`**. Editable installation is restricted to the primary `main` checkout so task-worktree cleanup cannot break the installed command.

Chezmoi automatic installation will follow the same fresh-machine bootstrap and daily-update pattern as my-git-utils. It is planned for `chezmoi init --apply`; plain `chezmoi init` only obtains the dotfiles source. The bootstrap has not been added to dotfiles yet.

Herdr configuration belongs to the chezmoi source repository. Edit its source in a topic worktree and review the rendered target; never edit `~/.config/herdr/config.toml` directly.

## Development

```sh
uv sync
uv run herdr-next-to-current --help
uv run herdr-next-to-current workspace --help
just check
```

`uv.lock` is tracked. Virtual environments, build outputs, and tool caches are ignored.

## Next step

Review the [workspace design and implementation sequence](PLAN.md), including the initial Git worktree group limit. Its final section contains the implementation request. No functional build or deployment is included in this design update.
