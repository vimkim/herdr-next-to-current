# Issue tracker: GitHub

Issues and specs live in GitHub Issues for `vimkim/herdr-next-to-current`. Use the `gh` CLI from this clone, or pass `--repo vimkim/herdr-next-to-current`.

## Conventions

- Create: `gh issue create --title "..." --body-file <file>`.
- Read: `gh issue view <number> --comments`; fetch labels with `--json labels`.
- List: `gh issue list --state open --json number,title,body,labels,comments`. Set an appropriate `--limit` and filters.
- Comment: `gh issue comment <number> --body-file <file>`.
- Update the body: `gh issue edit <number> --body-file <file>`.
- Labels: `gh issue edit <number> --add-label "..." --remove-label "..."`. Use the role mapping in `triage-labels.md`.
- Close: `gh issue close <number>`.

Use a temporary Markdown file for multiline bodies. Publishing a spec or ticket means creating a GitHub issue; fetching a ticket means reading that issue and its comments.

## Pull requests as a triage surface

**PRs as a request surface: no.**

GitHub issues and PRs share a number space. For an ambiguous reference, try `gh pr view <number>`, then `gh issue view <number>`.

## Wayfinding operations

- Map: one issue labelled `wayfinder:map`, containing Notes / Decisions-so-far / Fog.
- Child: create with `--parent <map-number>` and a `wayfinder:<type>` label (`research`, `prototype`, `grilling`, or `task`). If sub-issues are unavailable, add `Part of #<map-number>` to the child and a task-list link in the map.
- Blocking: use native dependencies via `gh issue edit <child> --add-blocked-by <blocker>`. If unavailable, record `Blocked by: #<number>` in the child body.
- Frontier: inspect the map's children in map order; choose the first open, unassigned child with no open blockers.
- Claim: `gh issue edit <number> --add-assignee @me` before starting work.
- Resolve: comment with the answer, close the child, and append a short answer plus link to the map's Decisions-so-far.
