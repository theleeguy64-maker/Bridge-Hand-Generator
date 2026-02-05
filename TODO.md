# TODOs

## Architecture

*Core work to make constructive help work for Profile E.*

1. [ ] **v1 constructive gates too conservative** *(highest risk)*
   - All 5 gates must pass; Profile E fails due to empty minima extraction
   - North is proven bottleneck (~95% of failures) but gets no help
   - **Fix options**:
     a. Make minima extraction work for RS/PC/OC constrained seats
     b. Add override: "if helper_seat identified with high confidence, try constructive"
   - **Why highest risk**: Core algorithm modification, could break profiles A-D

2. [ ] **V2 integration test suite**
   - Tests showing v2 policy actually improves deal generation
   - Proves the architecture changes have measurable impact

---

## Enhancements

*Nice-to-have features.*

3. [ ] **Metrics export CLI**
   - Export failure attribution to JSON/CSV
   - Per-seat, per-subprofile success histograms
   - Command: `python -m bridge_engine export-metrics <profile> [--boards N]`

---

## Unallocated

*v2 nonstandard constructive pieces - may be needed, may not.*

4. [ ] **Implement NS role filtering**
   - `ns_role_usage` field not yet enforced
   - Determines which subprofiles can be used based on driver/follower role

5. [ ] **Driver/follower classification**
   - `ns_role_for_seat` logic not complete
   - Determines which NS seat leads, which follows

6. [ ] **RS suit reordering by success rate**
   - Piece 2/3 partially implemented
   - Try RS suits in order of past success (explore vs exploit)

7. [ ] **PC/OC nudging**
   - Piece 4/5 partially implemented
   - When PC/OC fails, try alternate subprofiles for partner/opponent

---

## Summary

| Category | Remaining |
|----------|-----------|
| Architecture | **2** |
| Enhancements | 1 |
| Unallocated | 4 |
| **Total** | **7** |

## Notes

- **Branch**: `refactor/deal-generator`
- **Tests**: 231 passed, 4 skipped (intentional benchmarks)
- **Known working**: Profile A-D, deal generation, validation
- **Known struggling**: Profile E - constructive not engaging

---

## Completed Items (for reference)

<details>
<summary>30 items completed - click to expand</summary>

### Architecture (7 items)
- Refactor magic profile name checks (explicit flags)
- Expose constraint state to v2 policy (constraint_flags)
- Add "too hard = unviable" rule (early termination)
- Subprofile-level viability tracking (seat_subprofile_stats)
- HCP vs shape failure classification (seat_fail_hcp/shape counters)
- Connect attribution to helper policy (_is_shape_dominant_failure)
- "Standard vs nonstandard" analysis (merged into gates item)

### Latent Bugs (3 items)
- Mutating frozen dataclass
- Incomplete functions with no body
- Missing rng argument in function calls

### Dead Code (10 items)
- Missing list_drafts() function
- Duplicate SubProfile class
- Orphaned code fragments
- Duplicate function definitions
- Dead code in orchestrator.py
- Consolidated helper-seat functions
- Removed test profiles from production code

### Performance (1 item)
- O(n^2) list removal → set-based O(n)

### Code Quality (6 items)
- Invalid return type syntax
- Undefined Seat type
- Duplicate imports
- Typos
- Duplicate code in tests

### Future (3 items)
- Benchmark automation (BENCHMARKS.md)
- Failure report export (failure_report.py)
- Tests for untested modules

</details>
