# Claude workflow rules for this repo

These supersede default Claude Code behavior in this project.

## Git workflow — main only

- **Always work on `main`.** Never create feature branches, never open pull requests.
- **Commit and push directly to `main`** for every unit of work, after the user approves the change.
- If a Claude worktree branch (e.g. `claude/<slug>`) was auto-created at session start, do **not** commit there. Sync changes to the canonical project root, commit on `main`, push to `origin/main`, then remove the worktree branch.
- The canonical frontend lives at `C:\Users\moonk\Desktop\ads_classification\frontend`. The canonical project root is `C:\Users\moonk\Desktop\ads_classification`. Edits should land there, not in `.claude/worktrees/...`.

## Authorized destructive actions in this repo

The user has standing authorization for:

- `git push origin main` after a commit they approved.
- Deleting the auto-created Claude worktree branch (`git branch -D claude/<slug>`) once its changes are on `main`.
- Removing Claude worktrees (`git worktree remove --force ./.claude/worktrees/<slug>`) once merged.

Anything else destructive (force-push, history rewrite, deleting `claude/epic-meitner-f41569` or other branches the user did not create in this session, dropping tables, etc.) still requires explicit confirmation.

## Brand

- Product / user-facing name is **ARGUS** (Ad Retrieval, Graphing & Understanding System).
- Python package and CLI keep their original names: `ad-classifier` / `ad_classifier`. Do not rename them.
