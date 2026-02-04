# Generic Preferences for Claude

## Session Start
- Review `TODO.md` at the start of sessions and display the full contents verbosely (all pending items, all details)
- Reference `PROJECT_OVERVIEW.md` for high-level context (purpose, concepts, current state)
- Reference `ARCHITECTURE.md` for technical details (pipeline, data models, known issues)

## Shortcuts
- **"Lee Title"** - Change terminal title to "Bridge Hand Generator"
- **"Lee commit"** - Update CLAUDE.md, TODO.md, and ARCHITECTURE.md, then commit

## Documentation
- Proactively suggest updating `CLAUDE.md` when: new commands are added, project structure changes, new conventions are established, or key files are created/renamed
- After completing work, prompt: "Do you want to update CLAUDE.md, TODO.md, and ARCHITECTURE.md, then commit?"

## Code Quality
- Focus on the stability of large files - be careful with changes that could introduce bugs
- Prefer early returns and guard statements for error handling
- Put lots of remarks/comments in code for the benefit of all of us (future developers, Claude, and you)

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
- Before committing, always ask: "Do you want to update CLAUDE.md, TODO.md, and ARCHITECTURE.md, then commit?"
