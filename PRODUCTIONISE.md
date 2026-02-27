# Productionise - Bridge Hand Generator

## Goal

Take the Bridge Hand Generator from a working development prototype to a
polished, distributable application that a Mac user (without Python installed)
can receive as a single file/folder, run a simple setup, and start using.

## Target User

- macOS (Apple Silicon or Intel)
- No Python installed
- Comfortable with Terminal basics (cd, double-click)
- Receives a file from the developer (not via App Store or Homebrew)

## Current State

- Core engine works: v2 shape-help system, constrained deal generation, all profiles viable
- Interactive CLI via `python -m bridge_engine`
- 608 tests passing, 19 skipped
- No packaging (no pyproject.toml, no requirements.txt)
- No external dependencies beyond Python standard library
- No CI/CD pipeline
- No logging (print statements only)
- No error recovery in CLI flows (exceptions propagate or get swallowed)

## Distribution: High-Level Plan

### What we send the user

A single `.zip` file (e.g. `BridgeHandGenerator-v1.0.zip`) containing:

```
BridgeHandGenerator/
├── bridge_engine/          # The application code
├── profiles/               # Pre-built profile JSON files
├── setup.sh                # One-time setup script
├── run.sh                  # Launch script (double-clickable)
└── README.txt              # Plain-text quick start guide
```

### What setup.sh does (one-time, ~2 minutes)

1. **Check for Python 3.11+**
   - If found: use it
   - If not found: check for Homebrew, install Python via `brew install python@3.13`
   - If no Homebrew: install Homebrew first (official one-liner), then Python
   - Alternative: download the macOS Python installer from python.org automatically
2. **Create a virtual environment** inside the app folder (`BridgeHandGenerator/.venv`)
3. **Install the app** into the venv (`pip install -e .` or just verify imports work)
4. **Smoke test**: run `python -m bridge_engine --version` (or a quick import check)
5. **Print success message** with instructions to use `run.sh`

### What run.sh does (every launch)

1. Activate the `.venv`
2. Run `python -m bridge_engine`
3. User sees the main menu immediately

### Alternative: PyInstaller standalone binary

Instead of requiring Python installation, bundle everything into a single
macOS executable using PyInstaller:

```
pyinstaller --onefile --name bhg bridge_engine/__main__.py
```

Produces `dist/bhg` — a self-contained binary (~15-30 MB) the user can
double-click or run from Terminal. No Python needed on their machine.

**Trade-offs:**

| Approach | Pros | Cons |
|----------|------|------|
| **setup.sh + run.sh** | Small file (~200 KB), easy to update, profiles editable | Requires Python install step |
| **PyInstaller binary** | Zero dependencies, true double-click | Large file, harder to update, code signing needed for Gatekeeper |

**Decision**: Going with setup.sh approach (Option A). PyInstaller (Option B)
kept as a future alternative if the Python install step proves to be a barrier.

---

## Work Streams

### 1. Packaging & Distribution
- [ ] Add `pyproject.toml` with project metadata, dependencies, entry point
- [ ] Verify app has no external dependencies (only stdlib) — or list them
- [ ] Write `setup.sh` (Python check/install, venv creation, smoke test)
- [ ] Write `run.sh` (activate venv, launch app)
- [ ] Write `README.txt` (plain-text quick start for non-technical user)
- [ ] Build zip and test on a clean Mac (or clean user account)

### 2. Profile Review & Cleanup
- [ ] Review all 13 profiles: constraints, metadata, dealing order
- [ ] Run each profile through deal generation to confirm it works
- [ ] Update stale profile descriptions/authors if needed
- [ ] Verify sort_order values are correct

### 3. Documentation
- [ ] Update PROJECT_OVERVIEW.md (stale test count, stale "Remaining Work")
- [ ] Write a user-facing README.md (how to install, run, create profiles)
- [ ] Document profile JSON schema for users who edit manually

### 4. Error Handling & UX
- [ ] Audit CLI flows for unhandled exceptions
- [ ] Add graceful error messages for common failures (bad JSON, missing files)
- [ ] Consider adding logging (Python `logging` module) alongside/instead of print
- [ ] Review menu help text for completeness and accuracy

### 5. Testing Gaps
- [ ] Identify untested code paths (coverage report)
- [ ] Add integration tests for full CLI flows (main_menu end-to-end)
- [ ] Test with edge-case profiles (empty, single seat, max constraints)

### 6. CI/CD
- [ ] Add GitHub Actions workflow: pytest on push/PR
- [ ] Add Python version matrix (3.11, 3.12, 3.13)
- [ ] Consider adding linting (ruff/flake8)

### 7. Cleanup
- [ ] Remove `scripts/` backup files if no longer needed
- [ ] Review `.gitignore` for completeness
- [ ] Remove or archive the `cleanup/cli-menu` branch if fully merged
- [ ] Audit for any hardcoded paths or developer-specific defaults

## Priority Order

1. Profile review (low risk, high value — know what we're shipping)
2. Packaging (pyproject.toml + setup.sh + run.sh)
3. Error handling audit (user-facing app must not crash with tracebacks)
4. Documentation (README.txt for end user)
5. Build & test zip on clean Mac
6. CI/CD
7. Testing gaps
8. Cleanup
