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

### MAJOR (Performance / correctness risk)

4. [ ] **O(n^2) list removal** - `deal_generator.py:1112-1123`
   - Using `deck.remove(c)` in loop (O(n) search per removal)
   - Should use set operations: `deck_set -= chosen_set`
   - **Impact**: Slow for large iteration counts

5. [ ] **Duplicate function definitions** - `deal_generator.py`
   - `_weights_for_seat_profile`: lines 176 and 563
   - `_choose_index_for_seat`: likely duplicated as well
   - **Fix**: Remove duplicates, keep one canonical definition

### MINOR (Code quality)

6. [ ] **Invalid return type syntax** - `seat_viability.py:204, 349`
   - Uses `-> (bool, Optional[List[str]])` (parentheses)
   - Should be `-> Tuple[bool, Optional[List[str]]]`
   - **Impact**: Type checkers will complain; no runtime effect

7. [ ] **Overly broad `except Exception`** - multiple locations
   - `deal_generator.py`: lines 363, 690, 708
   - Catches all exceptions, masks real bugs
   - **Fix**: Catch specific exceptions or at minimum log them

8. [ ] **Missing `dealing_order` parameter** - `deal_generator.py:1145`
   - `_select_subprofiles_for_board()` at module level
   - May reference `dealing_order` without it being passed
   - **Verify**: Check if this is actually used or dead code

---

## Urgent - Architecture Fixes

### Constructive Help Not Firing

9. [ ] **v1 constructive gates too conservative** - Profile E gets no help
   - All 4 gates must pass; Profile E fails gate 2 or 3
   - North is proven bottleneck (~95% of failures) but gets no help
   - **Fix options**:
     a. Relax "standard only" gate - help any identified helper seat
     b. Make minima extraction work for RS/PC/OC constrained seats
     c. Add override: "if helper_seat identified with high confidence, try constructive"

10. [ ] **"Standard vs nonstandard" is wrong axis**
    - Current: Skip constructive for any seat with RS/PC/OC
    - Should be: "Is this seat failing for reasons constructive can help?"
    - **Fix**: Base decision on failure structure (HCP vs shape), not constraint type

---

## High Priority - Complete WIP Features

### Failure Attribution (Partially Done)

11. [ ] **HCP vs shape classification not implemented**
    - Counters exist: `seat_fail_hcp`, `seat_fail_shape`
    - Matcher doesn't classify failures yet
    - **Need**: `_match_seat` returns failure reason, not just bool
    - **Impact**: Can't decide "constructive appropriate here" without this

12. [ ] **Connect attribution to helper policy**
    - Once we know HCP vs shape split:
      - Shape-dominant failures → constructive is appropriate
      - HCP-dominant failures → constructive won't help; maybe declare unviable
    - **Not yet wired**

### Viability Declaration

13. [ ] **Add "too hard = unviable" rule**
    - Even after Stage 0-2 passes, profile may be effectively impossible
    - If best seat (with rotation) still fails > X% of attempts → declare unviable
    - **Current**: We grind forever on hopeless profiles
    - **Need**: Early termination with clear reason

---

## Medium Priority - Code Cleanup

14. [ ] **Consolidate helper-seat functions**
    - `_choose_hardest_seat_for_help()` vs `_choose_hardest_seat_for_board()`
    - Appear to do same thing with slightly different signatures
    - **Fix**: Merge into one function

15. [ ] **Remove test profiles from production code**
    - "Test profile", "Test_RandomSuit_W_PC_E" referenced in code
    - Should be in test fixtures only

16. [ ] **v2 policy seam returns empty dict**
    - `_nonstandard_constructive_v2_policy()` exists but does nothing
    - Either implement or remove dead code

---

## Future - Feature Work

### Phase 3: NS Role Semantics

17. [ ] **Implement NS role filtering**
    - `ns_role_usage` field exists ("any", "driver_only", "follower_only")
    - Not yet enforced during subprofile selection
    - **Need**: Filter subprofiles by role before index coupling

18. [ ] **Driver/follower classification**
    - Subprofiles have `ns_role_for_seat` ("driver", "follower", "neutral")
    - Logic to use this during generation not complete

### Constructive v2

19. [ ] **RS suit reordering by success rate**
    - Piece 2/3 partially implemented
    - Track which RS suit combinations succeed
    - Reorder to try successful combinations first

20. [ ] **PC/OC nudging**
    - Piece 4/5 partially implemented
    - When PC/OC fails, try alternate subprofiles
    - **Status**: Code exists, not tested/enabled

### Diagnostics

21. [ ] **Benchmark automation**
    - Profile E rotation benchmark is manual
    - Automate: run N profiles, report helper seats + expected success rates
    - Add to CI as slow/nightly test

22. [ ] **Failure report export**
    - Export attribution data to JSON/CSV for analysis
    - Current: only via debug hooks + print

---

## Notes

- **Branch**: `refactor/deal-generator`
- **Recent commits**: Failure attribution, v2 constructive pieces, Profile E benchmarks
- **Test coverage**: 59 test files, good coverage of core paths
- **Known working**: Profile A-D (easy), deal generation, validation
- **Known struggling**: Profile E (hard), constructive not engaging
