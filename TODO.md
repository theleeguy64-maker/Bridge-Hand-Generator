# TODOs

## Start Tasks
- [ ] Run profile management in program

---

## Architecture

### 1. [x] Base Smart Hand Order
- ✅ `_base_smart_hand_order()` in wizard_flow.py (5-priority algorithm)
- ✅ Risk-weighted ordering: `_compute_seat_risk()` handles multiple subprofiles

### 2. [x] v2 Shape-Based Help System (D0-D6)
- ✅ Extracted `_select_subprofiles_for_board()` to module level (D0)
- ✅ `SHAPE_PROB_GTE` table + `SHAPE_PROB_THRESHOLD` + `PRE_ALLOCATE_FRACTION` (D1)
- ✅ `_dispersion_check()` identifies tight seats (D2)
- ✅ `_random_deal()` helper (D3)
- ✅ `_pre_allocate()` — 50% of suit minima (D4)
- ✅ `_deal_with_help()` orchestrator (D5)
- ✅ `_build_single_constrained_deal_v2()` MVP (D6)
- Profiles A-D work. Profile E (shape+HCP) still too hard.

### 3. [ ] Full Attribution in v2 (D7)
- Add seat_fail_as_seat, global_other, global_unchecked, hcp, shape + debug hooks

### 4. [ ] Comparative Benchmarks (D8)
- Gated integration tests: v1 vs v2 on Profiles A/B/E

### 5. [ ] Swap v2 into Main Loop (D9)
- One-line change at `generate_deals()` call site

### 6. [ ] HCP Help
- Extend `_pre_allocate()` to bias toward high/low cards for tight HCP constraints
- Needed for Profile E (6 spades + 10-12 HCP)

---

## Enhancements

### 7. [ ] Metrics Export CLI
- `export-metrics <profile> [--boards N]`

---

## Summary
Architecture: 6 (2 done, 4 pending) | Enhancements: 1 | **Total: 7**

**Tests**: 353 passed, 4 skipped | **Branch**: refactor/deal-generator

---

## Completed (32 items)
<details>
<summary>Click to expand</summary>

- v2 shape-based help system: D0-D6 (dispersion check, pre-allocation, deal_with_help, v2 MVP)
- Magic profile name checks, constraint state to v2, "too hard = unviable" rule
- Subprofile viability tracking, HCP vs shape classification, attribution to policy
- Standard vs nonstandard analysis, default dealing order (Steps 1,3,4,5)
- Latent bugs (3), dead code (10), performance (1), code quality (6), future (3)

</details>
