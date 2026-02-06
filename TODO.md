# TODOs

## Start Tasks
- [ ] Run profile management in program

---

## Architecture

### 1. [x] Base Smart Hand Order
- ✅ `_base_smart_hand_order()` in wizard_flow.py (5-priority algorithm)
- ✅ Risk-weighted ordering: `_compute_seat_risk()` handles multiple subprofiles

### 2. [x] v2 Shape-Based Help System (D0-D8)
- ✅ Extracted `_select_subprofiles_for_board()` to module level (D0)
- ✅ `SHAPE_PROB_GTE` table + `SHAPE_PROB_THRESHOLD` + `PRE_ALLOCATE_FRACTION` (D1)
- ✅ `_dispersion_check()` identifies tight seats (D2)
- ✅ `_random_deal()` helper (D3)
- ✅ `_pre_allocate()` — 50% of suit minima (D4)
- ✅ `_deal_with_help()` orchestrator (D5)
- ✅ `_build_single_constrained_deal_v2()` MVP (D6)
- ✅ Full attribution: seat_fail_as_seat, global_other, global_unchecked, hcp, shape + debug hooks (D7)
- ✅ Gated benchmarks: v1 vs v2 on Profiles A/B/E (D8)
- Benchmark results: Profile B 3x faster, Profile E now generates all 100 boards

### 3. [x] Swap v2 into Main Loop (D9)
- ✅ One-line change at `generate_deals()` call site — v2 is now the active production path
- Profile E (6 spades + 10-12 HCP) now generates deals successfully

### 4. [x] Review deal_generator.py for old/unused code (stubs & flags)
- ✅ Removed 5 dead stub functions: `_build_rs_bucket_snapshot()`, `_nonstandard_constructive_help_enabled()`, `_v2_oc_nudge_try_alternates()`, `_v2_pc_nudge_try_alternates()`, `_v2_order_rs_suits_weighted()`
- ✅ Removed 2 always-False flags: `ENABLE_CONSTRUCTIVE_HELP`, `ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD`
- ✅ Removed 2 test-only debug hooks: `_DEBUG_NONSTANDARD_CONSTRUCTIVE_SHADOW`, `_DEBUG_NONSTANDARD_CONSTRUCTIVE_V2_POLICY`
- ✅ Simplified `_get_constructive_mode()` to always return all-False
- ✅ Deleted 7 test files, cleaned up 5 more (25 tests removed)
- deal_generator.py: 2,402 → 2,241 lines (−161)

### 4b. [ ] Remove cascading dead code from v1 builder
- Now that nonstandard flags are gone, several functions and inline code blocks inside the v1 builder are provably unreachable
- Candidates: `_shadow_probe_nonstandard_constructive()`, `_nonstandard_constructive_v2_policy()`, `_build_constraint_flags_per_seat()`, inline PC/OC nudge blocks, dead variables (rs_bucket_snapshot, seat_subprofile_stats, v2_policy)
- Also: shadow-related functions in `orchestrator.py` and admin menu item 4

### 5. [ ] HCP Help
- Extend `_pre_allocate()` to bias toward high/low cards for tight HCP constraints
- Needed for Profile E (6 spades + 10-12 HCP)

---

## Enhancements

### 7. [ ] Refactor large files
- `deal_generator.py` (2,241 lines) — split v1/v2, helpers, constants into separate modules
- `hand_profile_model.py` (921 lines) — split data models from logic
- `profile_cli.py` (968 lines) — split command handlers
- `orchestrator.py` (705 lines) — split session management from CLI routing

### 8. [ ] Metrics Export CLI
- `export-metrics <profile> [--boards N]`

---

## Summary
Architecture: 6 (4 done, 2 pending) | Enhancements: 2 | **Total: 6**

**Tests**: 337 passed, 4 skipped | **Branch**: refactor/deal-generator

---

## Completed (33 items)
<details>
<summary>Click to expand</summary>

- Dead code cleanup: removed 5 stubs, 2 flags, 2 hooks, simplified _get_constructive_mode (−161 lines, −25 tests)
- v2 shape-based help system: D0-D9 complete (dispersion check, pre-allocation, deal_with_help, v2 MVP, attribution, benchmarks, swap)
- Magic profile name checks, constraint state to v2, "too hard = unviable" rule
- Subprofile viability tracking, HCP vs shape classification, attribution to policy
- Standard vs nonstandard analysis, default dealing order (Steps 1,3,4,5)
- Latent bugs (3), dead code (10), performance (1), code quality (6), future (3)

</details>
