# TODOs

## Priority 1 - Architecture (The Real Work)

*These are the actual problems preventing constructive help from working.*
*Ordered by risk: least risky first → safest to tackle in sequence.*

1. [x] **HCP vs shape classification not implemented** *(medium risk)* ✅ DONE
   - `_match_standard()` returns `(bool, fail_reason)` with "hcp"/"shape" classification
   - `_match_subprofile()` and `_match_seat()` thread fail_reason through
   - `seat_fail_hcp` and `seat_fail_shape` counters now populated
   - 9 new unit tests in `test_match_standard_classification.py`

2. [x] **Connect attribution to helper policy** *(medium risk)* ✅ DONE
   - `_is_shape_dominant_failure()` checks HCP vs shape ratio before using constructive
   - `HardestSeatConfig.min_shape_ratio_for_constructive` configurable threshold (default 0.5)
   - Shape-dominant → constructive appropriate; HCP-dominant → skip constructive
   - 8 new unit tests in `test_attribution_to_policy.py`

3. [ ] **"Standard vs nonstandard" is wrong axis** *(medium-high risk)*
   - Current: Skip constructive for any seat with RS/PC/OC
   - Should be: "Is this seat failing for reasons constructive can help?"
   - **Fix**: Base decision on failure structure (HCP vs shape), not constraint type
   - **Why med-high risk**: Fundamental decision logic change

4. [ ] **v1 constructive gates too conservative** *(highest risk - do last)*
   - All 4 gates must pass; Profile E fails gate 2 or 3
   - North is proven bottleneck (~95% of failures) but gets no help
   - **Fix options**:
     a. Relax "standard only" gate - help any identified helper seat
     b. Make minima extraction work for RS/PC/OC constrained seats
     c. Add override: "if helper_seat identified with high confidence, try constructive"
   - **Why highest risk**: Core algorithm modification, could break profiles A-D

---

## Priority 6 - Future (Deferred)

5. [ ] **Metrics export CLI**
   - Export failure attribution to JSON/CSV
   - Per-seat, per-subprofile success histograms
   - Command: `python -m bridge_engine export-metrics <profile> [--boards N]`

6. [ ] **V2 integration test suite**
   - Tests showing v2 policy actually improves deal generation

7. [ ] **Implement NS role filtering**
   - `ns_role_usage` field not yet enforced

8. [ ] **Driver/follower classification**
   - `ns_role_for_seat` logic not complete

9. [ ] **RS suit reordering by success rate** *(blocked until P1 done)*
   - Piece 2/3 partially implemented

10. [ ] **PC/OC nudging** *(blocked until P1 done)*
    - Piece 4/5 partially implemented

---

## Summary

| Priority | Category | Remaining |
|----------|----------|-----------|
| 1 | Architecture | **2** |
| 6 | Future | 6 (deferred) |
| | **Total** | **8** |

### Dependency Graph

```
Core Classification:
  Item 1 (HCP vs Shape) ──► Item 2 (Attribution → Policy)
                                    │
                                    ▼
                           Items 3-4 (Gate Relaxation)
```

## Notes

- **Branch**: `refactor/deal-generator`
- **Tests**: 231 passed, 4 skipped (intentional benchmarks)
- **Known working**: Profile A-D, deal generation, validation
- **Known struggling**: Profile E - constructive not engaging

## Completed Items (for reference)

<details>
<summary>29 items completed - click to expand</summary>

### Priority 1 (6 items)
- Refactor magic profile name checks (explicit flags)
- Expose constraint state to v2 policy (constraint_flags)
- Add "too hard = unviable" rule (early termination)
- Subprofile-level viability tracking (seat_subprofile_stats)
- HCP vs shape failure classification (seat_fail_hcp/shape counters)
- Connect attribution to helper policy (_is_shape_dominant_failure)

### Priority 2 - Latent Bugs (3 items)
- Mutating frozen dataclass
- Incomplete functions with no body
- Missing rng argument in function calls

### Priority 3 - Dead Code (10 items)
- Missing list_drafts() function
- Duplicate SubProfile class
- Orphaned code fragments
- Duplicate function definitions
- Dead code in orchestrator.py
- Consolidated helper-seat functions
- Removed test profiles from production code

### Priority 4 - Performance (1 item)
- O(n^2) list removal → set-based O(n)

### Priority 5 - Code Quality (6 items)
- Invalid return type syntax
- Undefined Seat type
- Duplicate imports
- Typos
- Duplicate code in tests

### Priority 6 - Future (3 items)
- Benchmark automation (BENCHMARKS.md)
- Failure report export (failure_report.py)
- Tests for untested modules

</details>
