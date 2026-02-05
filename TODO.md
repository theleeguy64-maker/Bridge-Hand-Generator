# TODOs

## Start Tasks
- [ ] Run profile management in program

---

## Architecture

### 1. [x] Basic Smart Order
- ✅ `_smart_dealing_order()` in wizard_flow.py (5-priority algorithm)
- ✅ Risk-weighted ordering: `_compute_seat_risk()` handles multiple subprofiles

### 2. [ ] Determine Helper Method
- Decide: random draw vs enhanced deal method?
- RS reordering: try suits by past success
- v1 gates: empty minima extraction blocks RS/PC/OC

### 3. [ ] Random Draw Method
- Confirm current random draw works correctly

### 4. [ ] Enhanced Deal Method
- Constructive help for nonstandard seats: PC/OC nudging
- NS role filtering: filter subprofiles by driver_only/follower_only at deal time

### 5. [ ] V2 Policy Validation
- Integration tests: prove v2 policy improves success

---

## Enhancements

### 6. [ ] Metrics Export CLI
- `export-metrics <profile> [--boards N]`

---

## Summary
Architecture: 5 (1 done, 4 pending) | Enhancements: 1 | **Total: 6**

**Tests**: 287 passed, 4 skipped | **Branch**: refactor/deal-generator

---

## Completed (31 items)
<details>
<summary>Click to expand</summary>

- Magic profile name checks, constraint state to v2, "too hard = unviable" rule
- Subprofile viability tracking, HCP vs shape classification, attribution to policy
- Standard vs nonstandard analysis, default dealing order (Steps 1,3,4,5)
- Latent bugs (3), dead code (10), performance (1), code quality (6), future (3)

</details>
