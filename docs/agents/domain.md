# Domain Docs

This repository uses a single-context layout: `GLOSSARY.md` at the root and decisions under `docs/adr/`.

## Before exploring

Read the root `GLOSSARY.md` and ADRs relevant to the area being explored. If a root `GLOSSARY-MAP.md` exists later, follow its pointers to relevant context glossaries and also check their `src/<context>/docs/adr/` directories.

If these files are absent, proceed silently. Create them lazily through `domain-modeling`, including during `grill-with-docs`, when a term or decision is resolved.

## Vocabulary and decisions

Use glossary terms in issue titles, specifications, hypotheses, refactor proposals, and test names. If a needed concept is missing, reconsider the wording or note the gap for `domain-modeling`.

If proposed work contradicts an existing ADR, identify that ADR and explain why the decision should be reopened.
