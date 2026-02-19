# Generic Preferences for Claude

## Session Start
- Review `TODO.md` at the start of sessions and display the full contents verbosely (all pending items, all details)
- Reference `PROJECT_OVERVIEW.md` for high-level context (purpose, concepts, current state)
- Reference `ARCHITECTURE.md` for technical details (pipeline, data models, known issues)

## Shortcuts
- **"Lee Title"** - Change terminal title to "Bridge Hand Generator"
- **"Lee commit"** - Update CLAUDE.md, TODO.md, and ARCHITECTURE.md, then commit, then git push, then output "/usage" so user can check usage
- **"Lee code review"** - Run pyright (`npx pyright bridge_engine/`), then perform a full code review of all `bridge_engine/` files looking for: bugs, dead code, incorrect types, missing imports, unreachable code, narrowable exceptions, inconsistent naming, stale comments/docstrings. Present findings grouped by severity (A=bugs, B=dead code, C=consistency, D=simplification). Use "Lee slow" mode for all fixes.
- **"Lee slow"** - Careful mode. After EACH code change:
  1. Run tests (`.venv/bin/pytest -v`)
  2. If passed: Explicitly state "✅ All X tests passed"
  3. If failed: STOP and give 3 options:
     - **Review further** - investigate what went wrong
     - **Fix** - attempt to fix the issue
     - **Restore** - revert to prior code

## Documentation
- Proactively suggest updating `CLAUDE.md` when: new commands are added, project structure changes, new conventions are established, or key files are created/renamed
- After completing work, prompt: "Do you want to update CLAUDE.md and TODO.md, then commit?"

## Code Quality
- Focus on the stability of large files - be careful with changes that could introduce bugs
- Prefer early returns and guard statements for error handling
- Put lots of remarks/comments in code for the benefit of all of us (future developers, Claude, and you)

## Linting & Formatting (ruff)
- Run ruff after code changes: `.venv/bin/ruff check bridge_engine/ tests/` + `.venv/bin/ruff format bridge_engine/ tests/`
- Config in `ruff.toml` — per-file ignores for facades, late imports, and test patterns
- Keep ruff at 0 errors before committing

## Type Checking (pyright)
- Run pyright after code changes: `npx pyright bridge_engine/`
- Keep pyright at 0 errors — fix any new type errors before committing

## Testing
- Run the full test suite after every change to ensure no bugs are introduced
- Write extensive and specific tests - thorough coverage is preferred
- Never skip tests unless explicitly agreed
- Find bugs early - test frequently during development, not just at the end

## Planning
- Focus on low-risk, incremental changes with heavy testing at each step
- Avoid big-bang changes - break work into small, testable pieces

## Committing
- Keep pushing to commit regularly
- Before committing, always ask: "Do you want to update CLAUDE.md and TODO.md, then commit?"
