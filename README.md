# herdr-next-to-current

A standalone Python uv tool for opening Herdr tabs and workspaces immediately after the current item.

**Status: initial scaffold.** The installed command provides `--help`, `--version`, and the proposed `workspace` / `tab` interface. Creation currently exits with an explicit error and makes no Herdr changes. The implementation and chezmoi integration are described in [PLAN.md](PLAN.md).

## Intended commands

```sh
herdr-next-to-current workspace --label review
herdr-next-to-current tab --label logs
herdr-next-to-current tab --cwd ~/project --no-focus
```

The planned workflow captures the current item, creates a new one, repositions it, verifies the order, and focuses it unless `--no-focus` was requested. It uses Herdr's socket API, rather than maintaining a Herdr fork.

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

## Next flow

The `ask-matt` route is project setup, then `grill-with-docs` to settle the remaining design choices. The ready-to-use next prompt is in [PLAN.md](PLAN.md#next-prompt).
