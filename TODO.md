# TODOs

## Priority 1 - Architecture (The Real Work)

*These are the actual problems preventing constructive help from working.*

1. [ ] **v1 constructive gates too conservative** - Profile E gets no help
   - All 4 gates must pass; Profile E fails gate 2 or 3
   - North is proven bottleneck (~95% of failures) but gets no help
   - **Fix options**:
     a. Relax "standard only" gate - help any identified helper seat
     b. Make minima extraction work for RS/PC/OC constrained seats
     c. Add override: "if helper_seat identified with high confidence, try constructive"

2. [ ] **"Standard vs nonstandard" is wrong axis**
   - Current: Skip constructive for any seat with RS/PC/OC
   - Should be: "Is this seat failing for reasons constructive can help?"
   - **Fix**: Base decision on failure structure (HCP vs shape), not constraint type

3. [ ] **HCP vs shape classification not implemented**
   - Counters exist: `seat_fail_hcp`, `seat_fail_shape` - never populated
   - Matcher doesn't classify failures yet
   - **Need**: `_match_seat` returns failure reason, not just bool
   - **Location**: `seat_viability.py:_match_subprofile()` and `_match_standard()`
   - **Impact**: Can't decide "constructive appropriate here" without this

4. [ ] **Connect attribution to helper policy**
   - Once we know HCP vs shape split:
     - Shape-dominant failures → constructive is appropriate
     - HCP-dominant failures → constructive won't help; maybe declare unviable
   - **Not yet wired**

5. [ ] **Add "too hard = unviable" rule**
   - Even after Stage 0-2 passes, profile may be effectively impossible
   - If best seat (with rotation) still fails > X% of attempts → declare unviable
   - **Current**: We grind forever on hopeless profiles
   - **Need**: Early termination with clear reason

6. [ ] **Subprofile-level viability tracking** *(moved from P6)*
   - Currently only track per-seat viability
   - Need: `(success_count, attempt_count)` per subprofile per seat
   - **Impact**: Piece 4/5 nudging can pick best alternate subprofile instead of blind iteration

7. [ ] **Expose constraint state to v2 policy** *(moved from P6)*
   - V2 policy seam receives viability/attribution but NOT:
     - Which seats have PC constraints active
     - Which seats have OC constraints active
     - Which seats have RS constraints active
   - **Impact**: Policy can make constraint-aware decisions

---

## Priority 2 - Latent Bugs (Fix Before Enabling v2)

*Code works now because these paths are disabled. Will crash if enabled.*

8. [x] ~~**Mutating frozen dataclass** - `deal_generator.py`~~ **DONE**
   - Removed entire "Piece 2/6: RS re-ordering" block (~50 lines)
   - Was triple-broken: wrong attribute name, frozen mutation, rng.sample ignores order
   - Proper v2 RS reordering needs fresh design (see Priority 6)

9. [x] ~~**Incomplete functions with no body** - `deal_generator.py`~~ **DONE**
   - Removed `_constructive_sample_hand_min_first()` (was docstring only)
   - Removed `_debug_build_many_boards_with_stats()` (was docstring only)

10. [x] ~~**Missing `rng` argument in function calls** - `deal_generator.py`~~ **DONE**
   - Removed entire module-level `_select_subprofiles_for_board()` (~107 lines)
   - Had broken `_choose_index_for_seat(driver_sp)` calls missing `rng` argument
   - Nested version inside `_build_single_constrained_deal` is the one actually used

---

## Priority 3 - Dead Code Cleanup

*Confusing but harmless. Clean up when convenient.*

11. [x] ~~**Missing function** - `profile_store.py`~~ **DONE**
    - Added `list_drafts()` function

12. [x] ~~**Duplicate SubProfile class + orphaned code** - `hand_profile_model.py`~~ **DONE**
    - Removed first SubProfile (was lines 384-450)
    - Removed orphaned `from_dict` (was line 453)

13. [x] ~~**Orphaned code fragment** - `deal_generator.py:365`~~ **DONE**
    - Removed `passrandom_suit_choices` merge artifact

14. [x] ~~**Duplicate function definitions** - `deal_generator.py`~~ **PARTIALLY DONE**
    - Removed duplicate `_weights_for_seat_profile`
    - Removed duplicate `_choose_index_for_seat`
    - **Remaining**: module-level `_select_subprofiles_for_board` (deferred - high risk)

15. [x] ~~**Duplicate function** - `orchestrator.py`~~ **DONE**
    - Removed first `_format_nonstandard_rs_buckets()`

16. [x] ~~**Duplicate function + stub shadowing** - `profile_cli.py`~~ **DONE**
    - Removed stub, added `run_draft_tools()` wrapper

17. [x] ~~**Dead code in orchestrator.py**~~ **DONE**
    - Removed unreachable try-except block

18. [x] ~~**v2 policy seam returns empty dict**~~ **NOT A BUG**
    - `_nonstandard_constructive_v2_policy()` returns `{}` by design when v2 disabled
    - Tests actively use the debug hook (`test_nonstandard_v2_policy_seam.py`)
    - Working as intended - it's a seam, not dead code

19. [x] ~~**Consolidate helper-seat functions**~~ **DONE**
    - Removed `_choose_hardest_seat_for_help()` (~65 lines) - was never called
    - `_choose_hardest_seat_for_board()` is the one actually used

20. [x] ~~**Remove test profiles from production code**~~ **PARTIAL**
    - Removed unused `rs_w_pc_relaxed_mode` flag (set but never read)
    - Magic string checks remain - refactoring deferred to item 36

---

## Priority 4 - Performance

21. [x] ~~**O(n^2) list removal** - `deal_generator.py`~~ **DONE**
    - Changed `for c in chosen: deck.remove(c)` to set-based O(n) filtering
    - `deck[:] = [c for c in deck if c not in chosen_set]`

---

## Priority 5 - Code Quality

*Type hints, imports, typos. Fix when touching these files.*

22. [x] ~~**Invalid return type syntax** - `seat_viability.py`~~ **DONE**
    - Changed `-> (bool, ...)` to `-> Tuple[bool, ...]`

23. [x] ~~**Overly broad `except Exception`** - `deal_generator.py`~~ **SKIP**
    - Intentional defensive coding for batch jobs
    - Prevents single-deal failures from crashing entire generation

24. [x] ~~**Undefined `Seat` type** - `hand_profile_validate.py`~~ **DONE**
    - Added `Seat = str` type alias

25. [x] ~~**Duplicate imports** - multiple files~~ **DONE**
    - Cleaned up `lin_tools.py`, `cli_io.py`, `profile_wizard.py`

26. [x] ~~**Typo** - `profile_cli.py:343`~~ **DONE**
    - Fixed "chnaged" → "changed"

27. [x] ~~**Duplicate code in test** - `test_profile_e_failure_attribution.py`~~ **DONE**
    - Removed duplicate lines 95-100

---

## Priority 6 - Future

### V2 Tooling

28. [ ] **Metrics export CLI**
    - Export failure attribution to JSON/CSV
    - Per-seat, per-subprofile success histograms
    - Command: `python -m bridge_engine export-metrics <profile> [--boards N]`
    - **Impact**: Benchmark improvements vs baselines (Profile E case)

29. [ ] **V2 integration test suite**
    - Current v2 tests only check hook mechanics
    - Need: Tests showing v2 policy actually improves deal generation
    - Pattern: Generate N boards with v2 on vs off, compare success rates
    - **Impact**: Confidence that v2 changes help rather than hurt

### NS Role Semantics (Deferred)

30. [ ] **Implement NS role filtering**
    - `ns_role_usage` field exists ("any", "driver_only", "follower_only")
    - Not yet enforced during subprofile selection

31. [ ] **Driver/follower classification**
    - Subprofiles have `ns_role_for_seat` ("driver", "follower", "neutral")
    - Logic not complete

### Constructive v2 Implementation (Blocked Until P1 Items 3, 6, 7 Done)

32. [ ] **RS suit reordering by success rate**
    - Piece 2/3 partially implemented

33. [ ] **PC/OC nudging**
    - Piece 4/5 partially implemented

### Diagnostics

34. [ ] **Benchmark automation**
    - Profile E rotation benchmark is manual
    - Add to CI as slow/nightly test

35. [ ] **Failure report export**
    - Export attribution data to JSON/CSV

### Test Coverage (Expanded for V2-Critical Modules)

36. [ ] **Add tests for untested modules**
    - `hand_profile_validate.py` (20KB) - core validation before all deal gen
    - `profile_viability.py` (7KB) - viability classification
    - `profile_convert.py` - has file I/O logic, schema migration

### Code Quality

37. [ ] **Refactor magic profile name checks**
    - `"Test profile"` → sets `is_invariants_safety_profile` based on name
    - `"Test_RandomSuit_W_PC_E"` → routes to special code path based on name
    - Should use explicit flags set by tests, not magic strings in production
    - Affects: `hand_profile_model.py`, `deal_generator.py`, 7 test files

---

## Summary

| Priority | Category | Total | Done | Remaining |
|----------|----------|-------|------|-----------|
| 1 | Architecture | 7 | 0 | **7** |
| 2 | Latent Bugs | 3 | 3 | 0 |
| 3 | Dead Code | 10 | 10 | 0 |
| 4 | Performance | 1 | 1 | 0 |
| 5 | Code Quality | 6 | 6 | 0 |
| 6 | Future | 10 | 0 | 10 |
| | **Total** | **37** | **20** | **17** |

### V2 Dependency Graph

```
Item 3 (Failure Classifier) ──────┐
                                  ├──► Items 32-33 (V2 Implementation)
Item 6 (Subprofile Viability) ────┤
                                  │
Item 7 (Constraint State) ────────┘

Item 28 (Metrics Export) ──► Benchmarking / Tuning

Item 29 (Integration Tests) ──► Confidence in V2 changes
```

## Notes

- **Branch**: `refactor/deal-generator`
- **Tests**: 161 passed, 4 skipped (intentional benchmarks)
- **Known working**: Profile A-D, deal generation, validation
- **Known struggling**: Profile E - constructive not engaging
