# Productionise TODO

## In Progress
(none)

## Pending

### 1. Profile Review
- [ ] Review all 13 profiles end-to-end (constraints, metadata, generation)
- [ ] Run each profile through deal generation to confirm it works
- [ ] Verify sort_order values are correct

### 2. Packaging (Option A: setup.sh + run.sh)
- [ ] Create `pyproject.toml` with metadata + entry point
- [ ] Verify no external dependencies (only stdlib)
- [ ] Write `setup.sh` — check/install Python, create venv, smoke test
- [ ] Write `run.sh` — activate venv, launch app
- [ ] Test clean install in fresh venv

### 3. Error Handling
- [ ] Audit CLI for unhandled exceptions (no raw tracebacks for end user)
- [ ] Add graceful error messages for common failures
- [ ] Review menu help text for completeness

### 4. Documentation
- [ ] Update PROJECT_OVERVIEW.md (stale sections)
- [ ] Write `README.txt` (plain-text quick start for end user)
- [ ] Document profile JSON schema

### 5. Build & Test
- [ ] Build zip with app code + profiles + setup.sh + run.sh + README.txt
- [ ] Test on clean Mac (or clean user account)

### 6. CI/CD
- [ ] GitHub Actions: pytest on push/PR
- [ ] Python version matrix (3.11-3.13)

### 7. Cleanup
- [ ] Review scripts/ directory
- [ ] Review .gitignore
- [ ] Audit hardcoded defaults

### Future: Option B (PyInstaller)
- [ ] PyInstaller standalone binary (if Python install is a barrier)

---

## Done
(none yet)
