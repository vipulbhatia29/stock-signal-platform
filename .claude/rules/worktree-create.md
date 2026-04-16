---
description: EnterWorktree defaults to main — always verify and reset to origin/develop after creating a worktree
---

# Worktree Creation Discipline

Claude Code's `EnterWorktree` tool creates new worktrees based on the repository's **default branch** (`main`), not `develop`. The tool does not expose a `base_branch` parameter, so the fix must happen *after* the worktree is created.

This has bitten us multiple times (see Serena memory `feedback_worktree_branch_base` and KAN-430 ticket). If the new worktree is based on a stale `main` tip, all recent `develop` PRs are missing, leading to phantom imports, test failures, and wasted cherry-picks.

## The Rule

**Immediately after every `EnterWorktree` call**, run this check-and-fix block in the new worktree's directory:

```bash
git status && git log --oneline -3
```

If `HEAD` is not at `origin/develop`'s tip (which is the expected base for every `feat/*`, `chore/*`, and `fix/*` branch), reset:

```bash
git fetch origin develop
git reset --hard origin/develop
```

Then re-confirm:

```bash
git log --oneline -3   # should now match origin/develop tip
```

## When NOT to reset

- **Hotfix branches** (`hotfix/*`) intentionally branch from `main`. For those, the `EnterWorktree` default is correct and no reset is needed.
- **Experimental worktrees** explicitly based on another branch (rare). Verify intent before resetting.

If in doubt, check the ticket: `feat/KAN-*` and `chore/KAN-*` always target `develop`; only `hotfix/KAN-*` targets `main`.

## Why not automate with a hook?

A `PostToolUse` hook on `EnterWorktree` that auto-resets is **destructive** — `git reset --hard` would wipe any commits intentionally made on a different base (e.g., hotfix worktrees). The discipline-based fix is safe and deterministic when followed.

If this rule proves insufficient after adoption, a *warning-only* hook (print diff between new worktree `HEAD` and `origin/develop`) can be added as a follow-up ticket.

## Related

- `feedback_worktree_branch_base.md` (auto-memory) — original incident log
- KAN-430 — ticket that mandated this rule
- CLAUDE.md `## Git Branching` section — "ALWAYS branch from develop"
