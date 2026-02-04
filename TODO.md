# TODOs

## Urgent - Code Review Fixes

### CRITICAL (Blocking correctness)

1. [ ] **Duplicate SubProfile class + orphaned code** - `hand_profile_model.py`
   - SubProfile defined TWICE: lines 384 and 503
   - Second definition (503) overwrites first, has working `from_dict`
   - Orphaned `from_dict` at line 453 (module level, dead code)
   - First SubProfile (384-451) is completely dead code
   - **Impact**: Works but confusing; dead code should be removed

2. [ ] **Orphaned code fragment** - `deal_generator.py:365`
   - Line reads: `passrandom_suit_choices: Dict[Seat, List[str]] = {}`
   - `pass` merged with next statement (likely merge conflict artifact)
   - **Impact**: Syntax error or unexpected behavior

3. [ ] **Mutating frozen dataclass** - `deal_generator.py:1689, 1707`
   - Attempts to set `rs_constraint.suits = list(reordered)` on frozen dataclass
   - Will raise `FrozenInstanceError` at runtime
   - **Fix**: Use `dataclasses.replace()` to create modified copy

4. [ ] **Incomplete functions with no body** - `deal_generator.py`
   - `_constructive_sample_hand_min_first()` lines 1128-1143: docstring only, no body
   - `_debug_build_many_boards_with_stats()` lines 2026-2042: docstring only, no body
   - **Impact**: Will crash if called

5. [ ] **Missing `rng` argument in function calls** - `deal_generator.py`
   - Line 1186: `profile.ns_driver_seat(rng)` but `rng` undefined in scope
   - Lines 1201, 1232: `_choose_index_for_seat(driver_sp)` missing `rng` argument
   - **Impact**: NameError at runtime

### MAJOR (Performance / correctness risk)

6. [ ] **O(n^2) list removal** - `deal_generator.py:1112-1123`
   - Using `deck.remove(c)` in loop (O(n) search per removal)
   - Should use set operations: `deck_set -= chosen_set`
   - **Impact**: Slow for large iteration counts

7. [ ] **Duplicate function definitions** - `deal_generator.py`
   - `_weights_for_seat_profile`: lines 176-198 and 563-585 (identical)
   - `_choose_index_for_seat`: lines 201-212 and 745-759 (near identical)
   - `_select_subprofiles_for_board`: module level AND nested inside `_build_single_constrained_deal`
   - **Fix**: Remove duplicates, keep one canonical definition

8. [ ] **Duplicate function** - `orchestrator.py`
   - `_format_nonstandard_rs_buckets()` defined twice: lines 119-159 and 224-264
   - **Fix**: Remove duplicate

9. [ ] **Duplicate function + stub shadowing** - `profile_cli.py`
   - `draft_tools_action()` defined at line 288 (full implementation)
   - Also defined at line 958 (stub: "not implemented")
   - Stub shadows real implementation
   - **Fix**: Remove stub at line 958

10. [ ] **Missing function** - `profile_store.py`
    - `profile_cli.py:290` calls `profile_store.list_drafts(profiles_dir)`
    - Function `list_drafts()` never defined in `profile_store.py`
    - **Impact**: Runtime error when accessing draft tools

### MINOR (Code quality)

11. [ ] **Invalid return type syntax** - `seat_viability.py:204, 349`
    - Uses `-> (bool, Optional[List[str]])` (parentheses)
    - Should be `-> Tuple[bool, Optional[List[str]]]`
    - **Impact**: Type checkers will complain; no runtime effect

12. [ ] **Overly broad `except Exception`** - multiple locations
    - `deal_generator.py`: lines 363, 690, 708
    - Catches all exceptions, masks real bugs
    - **Fix**: Catch specific exceptions or at minimum log them

13. [ ] **Undefined `Seat` type** - `hand_profile_validate.py:267, 296`
    - Uses `Seat` in type annotations but never defined
    - **Fix**: Add `Seat = str` at top of file

14. [ ] **Duplicate imports** - multiple files
    - `lin_tools.py`: `Iterable`, `List`, `re` imported multiple times
    - `cli_io.py:79`: `Optional` already imported at line 5
    - `profile_wizard.py:21-23`: `HandProfile`, `validate_profile` imported twice
    - **Fix**: Consolidate imports

15. [ ] **Typo** - `profile_cli.py:343`
    - "chnaged" should be "changed"

16. [ ] **Duplicate code in test** - `test_profile_e_failure_attribution.py:88-100`
    - Lines 88-93 duplicated exactly at lines 95-100
    - **Fix**: Remove duplicate assignment block

---

## Urgent - Architecture Fixes

### Constructive Help Not Firing

17. [ ] **v1 constructive gates too conservative** - Profile E gets no help
    - All 4 gates must pass; Profile E fails gate 2 or 3
    - North is proven bottleneck (~95% of failures) but gets no help
    - **Fix options**:
      a. Relax "standard only" gate - help any identified helper seat
      b. Make minima extraction work for RS/PC/OC constrained seats
      c. Add override: "if helper_seat identified with high confidence, try constructive"

18. [ ] **"Standard vs nonstandard" is wrong axis**
    - Current: Skip constructive for any seat with RS/PC/OC
    - Should be: "Is this seat failing for reasons constructive can help?"
    - **Fix**: Base decision on failure structure (HCP vs shape), not constraint type

---

## High Priority - Complete WIP Features

### Failure Attribution (Partially Done)

19. [ ] **HCP vs shape classification not implemented**
    - Counters exist: `seat_fail_hcp`, `seat_fail_shape`
    - Matcher doesn't classify failures yet
    - **Need**: `_match_seat` returns failure reason, not just bool
    - **Impact**: Can't decide "constructive appropriate here" without this

20. [ ] **Connect attribution to helper policy**
    - Once we know HCP vs shape split:
      - Shape-dominant failures → constructive is appropriate
      - HCP-dominant failures → constructive won't help; maybe declare unviable
    - **Not yet wired**

### Viability Declaration

21. [ ] **Add "too hard = unviable" rule**
    - Even after Stage 0-2 passes, profile may be effectively impossible
    - If best seat (with rotation) still fails > X% of attempts → declare unviable
    - **Current**: We grind forever on hopeless profiles
    - **Need**: Early termination with clear reason

---

## Medium Priority - Code Cleanup

22. [ ] **Consolidate helper-seat functions**
    - `_choose_hardest_seat_for_help()` vs `_choose_hardest_seat_for_board()`
    - Appear to do same thing with slightly different signatures
    - **Fix**: Merge into one function

23. [ ] **Remove test profiles from production code**
    - "Test profile", "Test_RandomSuit_W_PC_E" referenced in code
    - Should be in test fixtures only

24. [ ] **v2 policy seam returns empty dict**
    - `_nonstandard_constructive_v2_policy()` exists but does nothing
    - Either implement or remove dead code

25. [ ] **Dead code in orchestrator.py:463-472**
    - Unreachable try-except block after successful return
    - **Fix**: Remove dead code

---

## Future - Feature Work

### Phase 3: NS Role Semantics

26. [ ] **Implement NS role filtering**
    - `ns_role_usage` field exists ("any", "driver_only", "follower_only")
    - Not yet enforced during subprofile selection
    - **Need**: Filter subprofiles by role before index coupling

27. [ ] **Driver/follower classification**
    - Subprofiles have `ns_role_for_seat` ("driver", "follower", "neutral")
    - Logic to use this during generation not complete

### Constructive v2

28. [ ] **RS suit reordering by success rate**
    - Piece 2/3 partially implemented
    - Track which RS suit combinations succeed
    - Reorder to try successful combinations first

29. [ ] **PC/OC nudging**
    - Piece 4/5 partially implemented
    - When PC/OC fails, try alternate subprofiles
    - **Status**: Code exists, not tested/enabled

### Diagnostics

30. [ ] **Benchmark automation**
    - Profile E rotation benchmark is manual
    - Automate: run N profiles, report helper seats + expected success rates
    - Add to CI as slow/nightly test

31. [ ] **Failure report export**
    - Export attribution data to JSON/CSV for analysis
    - Current: only via debug hooks + print

### Test Coverage

32. [ ] **Add tests for untested modules**
    - `profile_convert.py` - has file I/O logic, needs tests
    - `profile_print.py` - minimal, low priority
    - `wizard_constants.py` - constants only, low priority
    - `cli_prompts.py` - wrapper, low priority
    - `menu_help.py` - static data, low priority

---

## Notes

- **Branch**: `refactor/deal-generator`
- **Recent commits**: Failure attribution, v2 constructive pieces, Profile E benchmarks
- **Test coverage**: 56 test files, 165 tests, 161 passed, 4 skipped (intentional benchmarks)
- **Known working**: Profile A-D (easy), deal generation, validation
- **Known struggling**: Profile E (hard), constructive not engaging

### Issue Count Summary

| Severity | Count |
|----------|-------|
| Critical | 5 |
| Major | 5 |
| Minor | 6 |
| Architecture | 2 |
| High Priority | 3 |
| Medium Priority | 4 |
| Future | 7 |
| **Total** | **32** |
