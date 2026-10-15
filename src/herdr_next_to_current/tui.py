"""A numbered, fully expanded sidebar picker. No lock is held while typing."""

import curses

from .client import ClientError
from .placement import Changed, Outcome, PlacementError, move_before, read_state


def _safe(text):
    return "".join(c if c.isprintable() else "?" for c in str(text))


def picker(screen, client, source, on_error=None):
    screen.keypad(True)
    state = read_state(client)
    state.standalone(source)
    text, message, offset = "", "", 0
    unresolved = None
    while True:
        height, width = screen.getmaxyx()
        page = max(1, height - 7)
        offset = max(0, min(offset, max(0, len(state.rows) + 1 - page)))
        screen.erase()

        def put(y, value, height=height, width=width):
            if 0 <= y < height and width > 1:
                try:
                    screen.addnstr(y, 0, _safe(value), width - 1)
                except curses.error:
                    pass  # A wide glyph or a concurrent resize may reach the border.

        row = next((r for r in state.rows if r["workspace_id"] == source), None)
        put(0, f"Move Space: {row['label'] if row else source}")
        groups = state.groups
        for y, index in enumerate(range(offset, min(len(state.rows) + 1, offset + page)), 2):
            if index == len(state.rows):
                label = "[end of list]"
            else:
                row = state.rows[index]
                label = row["label"]
                if row["workspace_id"] == source:
                    label += "  current"
                if (row.get("worktree") or {}).get("repo_key") in groups:
                    label += "  [Git worktree group: unavailable]"
            put(y, f"{index + 1:>4}  {label}")
        put(height - 4, f"Insert current Space before number: {text}_")
        put(height - 3, "Enter: move  Esc/q: cancel  r: refresh  PgUp/PgDn: scroll")
        put(height - 2, message)
        screen.refresh()
        try:
            key = screen.get_wch()
        except curses.error:
            continue
        if key in ("q", "\x1b"):
            return unresolved or Outcome("cancelled", source, stage="cancelled")
        if key == curses.KEY_RESIZE:
            continue
        if key in (curses.KEY_NPAGE, curses.KEY_DOWN):
            offset += page if key == curses.KEY_NPAGE else 1
        elif key in (curses.KEY_PPAGE, curses.KEY_UP):
            offset -= page if key == curses.KEY_PPAGE else 1
        elif key in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            text = text[:-1]
        elif isinstance(key, str) and key in "0123456789" and len(text) < 12:
            text += key
        elif key == "-" and not text:
            text = "-"
        elif key == "r":
            try:
                state = read_state(client)
                text, message = "", "Refreshed; choose a number"
            except ClientError as error:
                message = str(error)
        elif key in ("\n", "\r", curses.KEY_ENTER):
            if not text or text == "-":
                message = "Enter a row number first"
                continue
            try:
                return move_before(client, source, number=int(text), frozen=state)
            except Changed as error:
                try:
                    state = read_state(client)
                    text = ""
                except ClientError as refresh_error:
                    message = str(refresh_error)
                    continue
                message = str(error)
            except (PlacementError, ClientError, OSError) as error:
                # The popup stays open, including after a failed move. No automatic retry.
                message = str(error)
                code = getattr(error, "code", 2)
                failure = Outcome(
                    "uncertain" if code == 4 else "error",
                    source,
                    stage=getattr(error, "stage", "validated"),
                    error=message,
                    code=code,
                )
                if on_error:
                    on_error(failure)
                if code == 4:
                    unresolved = failure
                    message += "; outcome uncertain; refresh before another move"
                text = ""


def run(client, source, on_error=None):
    try:
        return curses.wrapper(picker, client, source, on_error)
    except curses.error as error:
        raise PlacementError(f"terminal setup failed: {error}") from error
