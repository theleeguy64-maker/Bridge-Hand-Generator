# Bridge Hand Generator

**You are working in the Bridge Hand Generator project.** Always be aware of this context — the user should not need to tell you which project this is.

## Project
- **Path**: `~/Applications/BridgeHandGenerator/Exec`
- **Launcher**: `python -m bridge_engine` (CLI menu)
- **Description**: Generates bridge card deals satisfying complex constraint profiles (HCP ranges, suit lengths, contingent constraints) with shape-based help, failure attribution, and adaptive re-seeding.

## Optimization

**Project Weight:** Heavy  
**Message Threshold:** 24 messages  
**Default Model:** Opus  

**Feature Defaults:**
- Web Search: OFF (use Firecrawl for specific URLs)
- Advanced Thinking: OFF (enable for tricky bugs only)
- MCP Servers: Firebase ON, Firecrawl OFF, Context7 OFF

**Model Selection Guide**

| Task Type | Model | Why |
|-----------|-------|-----|
| Bug diagnosis | Opus | Complex multi-file logic; use full power |
| Quick fixes | Sonnet | Lighter; straightforward changes |
| Code review | Sonnet | Pattern matching; downgrade from default |
| Architecture/design | Opus | Keep default; needs deep thinking |
| Documentation | Haiku | Simplest task; no reasoning needed |
| Refactoring | Sonnet | Complex but structured; Sonnet sufficient |

**When to Start Fresh**

After 12 messages, run `lee status` to check message count and session age. If starting new work, run `lee fresh` for auto-fresh-chat with context pre-loaded.

## Tech Stack
| Layer | Technology |
|-------|------------|
| Language | Python 3.13 |
| Testing | pytest |
| Type Checking | pyright (0 errors, 28 files, 11.3K lines) |
| Linting | ruff (check + format) |
| Output | TXT + LIN format |

## Pointers
- See `ARCHITECTURE.md` for module structure, data model, pipeline, and architectural decisions
- See `PROJECT_OVERVIEW.md` for purpose, key concepts, and design principles
- See `TODO.md` for task tracking and code review history

## Common Commands
```bash
# Run
python -m bridge_engine

# Test
.venv/bin/pytest -v

# Lint + Format
.venv/bin/ruff check bridge_engine/ tests/
.venv/bin/ruff format bridge_engine/ tests/

# Type Check
npx pyright bridge_engine/
```

---

## Preferences for Claude

## Session Start
- Review `TODO.md` at the start of sessions and display the full contents verbosely (all pending items, all details)
- Reference `PROJECT_OVERVIEW.md` for high-level context (purpose, concepts, current state)
- Reference `ARCHITECTURE.md` for technical details (pipeline, data models, known issues)

## Lee Shortcuts, Testing, Planning
See global `~/.claude/CLAUDE.md` — Lee Shortcuts, testing policy, and planning conventions apply to all projects.

### Project-specific additions to Lee code review
- Run pyright first: `npx pyright bridge_engine/`
- Run ruff: `.venv/bin/ruff check bridge_engine/ tests/` + `.venv/bin/ruff format bridge_engine/ tests/`
- Keep both at 0 errors before committing

## Linting & Formatting
- **ruff**: `.venv/bin/ruff check bridge_engine/ tests/` + `.venv/bin/ruff format bridge_engine/ tests/`
- Config in `ruff.toml` — per-file ignores for facades, late imports, and test patterns
- **pyright**: `npx pyright bridge_engine/` — keep at 0 errors
