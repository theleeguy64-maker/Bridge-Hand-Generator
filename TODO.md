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
   - Counters exist: `seat_fail_hcp`, `seat_fail_shape`
   - Matcher doesn't classify failures yet
   - **Need**: `_match_seat` returns failure reason, not just bool
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

---

## Priority 2 - Latent Bugs (Fix Before Enabling v2)

*Code works now because these paths are disabled. Will crash if enabled.*

6. [x] ~~**Mutating frozen dataclass** - `deal_generator.py`~~ **DONE**
   - Removed entire "Piece 2/6: RS re-ordering" block (~50 lines)
   - Was triple-broken: wrong attribute name, frozen mutation, rng.sample ignores order
   - Proper v2 RS reordering needs fresh design (see Priority 6)

7. [x] ~~**Incomplete functions with no body** - `deal_generator.py`~~ **DONE**
   - Removed `_constructive_sample_hand_min_first()` (was docstring only)
   - Removed `_debug_build_many_boards_with_stats()` (was docstring only)

8. [x] ~~**Missing `rng` argument in function calls** - `deal_generator.py`~~ **DONE**
   - Removed entire module-level `_select_subprofiles_for_board()` (~107 lines)
   - Had broken `_choose_index_for_seat(driver_sp)` calls missing `rng` argument
   - Nested version inside `_build_single_constrained_deal` is the one actually used

---

## Priority 3 - Dead Code Cleanup

*Confusing but harmless. Clean up when convenient.*

9. [x] ~~**Missing function** - `profile_store.py`~~ **DONE**
   - Added `list_drafts()` function

10. [x] ~~**Duplicate SubProfile class + orphaned code** - `hand_profile_model.py`~~ **DONE**
    - Removed first SubProfile (was lines 384-450)
    - Removed orphaned `from_dict` (was line 453)

11. [x] ~~**Orphaned code fragment** - `deal_generator.py:365`~~ **DONE**
    - Removed `passrandom_suit_choices` merge artifact

12. [x] ~~**Duplicate function definitions** - `deal_generator.py`~~ **PARTIALLY DONE**
    - Removed duplicate `_weights_for_seat_profile`
    - Removed duplicate `_choose_index_for_seat`
    - **Remaining**: module-level `_select_subprofiles_for_board` (deferred - high risk)

13. [x] ~~**Duplicate function** - `orchestrator.py`~~ **DONE**
    - Removed first `_format_nonstandard_rs_buckets()`

14. [x] ~~**Duplicate function + stub shadowing** - `profile_cli.py`~~ **DONE**
    - Removed stub, added `run_draft_tools()` wrapper

15. [x] ~~**Dead code in orchestrator.py**~~ **DONE**
    - Removed unreachable try-except block

16. [x] ~~**v2 policy seam returns empty dict**~~ **NOT A BUG**
    - `_nonstandard_constructive_v2_policy()` returns `{}` by design when v2 disabled
    - Tests actively use the debug hook (`test_nonstandard_v2_policy_seam.py`)
    - Working as intended - it's a seam, not dead code

17. [x] ~~**Consolidate helper-seat functions**~~ **DONE**
    - Removed `_choose_hardest_seat_for_help()` (~65 lines) - was never called
    - `_choose_hardest_seat_for_board()` is the one actually used

18. [x] ~~**Remove test profiles from production code**~~ **PARTIAL**
    - Removed unused `rs_w_pc_relaxed_mode` flag (set but never read)
    - Magic string checks remain - refactoring deferred to item 33

---

## Priority 4 - Performance

19. [ ] **O(n^2) list removal** - `deal_generator.py`
    - Using `deck.remove(c)` in loop (O(n) search per removal)
    - Should use set operations: `deck_set -= chosen_set`
    - **Impact**: Slow but correct

---

## Priority 5 - Code Quality

*Type hints, imports, typos. Fix when touching these files.*

20. [ ] **Invalid return type syntax** - `seat_viability.py`
    - Uses `-> (bool, Optional[List[str]])` (parentheses)
    - Should be `-> Tuple[bool, Optional[List[str]]]`

21. [ ] **Overly broad `except Exception`** - `deal_generator.py`
    - Catches all exceptions, masks real bugs

22. [ ] **Undefined `Seat` type** - `hand_profile_validate.py`
    - Uses `Seat` in annotations but never defined
    - **Fix**: Add `Seat = str` at top of file

23. [ ] **Duplicate imports** - multiple files
    - `lin_tools.py`: `Iterable`, `List`, `re` imported multiple times
    - `cli_io.py`: `Optional` already imported
    - `profile_wizard.py`: `HandProfile`, `validate_profile` imported twice

24. [ ] **Typo** - `profile_cli.py:343`
    - "chnaged" should be "changed"

25. [ ] **Duplicate code in test** - `test_profile_e_failure_attribution.py`
    - Lines 88-93 duplicated exactly at lines 95-100

---

## Priority 6 - Future

### Phase 3: NS Role Semantics

26. [ ] **Implement NS role filtering**
    - `ns_role_usage` field exists ("any", "driver_only", "follower_only")
    - Not yet enforced during subprofile selection

27. [ ] **Driver/follower classification**
    - Subprofiles have `ns_role_for_seat` ("driver", "follower", "neutral")
    - Logic not complete

### Constructive v2

28. [ ] **RS suit reordering by success rate**
    - Piece 2/3 partially implemented

29. [ ] **PC/OC nudging**
    - Piece 4/5 partially implemented

### Diagnostics

30. [ ] **Benchmark automation**
    - Profile E rotation benchmark is manual
    - Add to CI as slow/nightly test

31. [ ] **Failure report export**
    - Export attribution data to JSON/CSV

### Test Coverage

32. [ ] **Add tests for untested modules**
    - `profile_convert.py` - has file I/O logic, needs tests
    - Others are low priority (minimal/static)

### Code Quality

33. [ ] **Refactor magic profile name checks**
    - `"Test profile"` → sets `is_invariants_safety_profile` based on name
    - `"Test_RandomSuit_W_PC_E"` → routes to special code path based on name
    - Should use explicit flags set by tests, not magic strings in production
    - Affects: `hand_profile_model.py`, `deal_generator.py`, 7 test files

---

## Summary

| Priority | Category | Total | Done | Remaining |
|----------|----------|-------|------|-----------|
| 1 | Architecture | 5 | 0 | 5 |
| 2 | Latent Bugs | 3 | 3 | 0 |
| 3 | Dead Code | 10 | 10 | 0 |
| 4 | Performance | 1 | 0 | 1 |
| 5 | Code Quality | 6 | 0 | 6 |
| 6 | Future | 8 | 0 | 8 |
| | **Total** | **33** | **13** | **20** |

## Notes

- **Branch**: `refactor/deal-generator`
- **Tests**: 161 passed, 4 skipped (intentional benchmarks)
- **Known working**: Profile A-D, deal generation, validation
- **Known struggling**: Profile E - constructive not engaging
