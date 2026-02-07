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

### 4b. [x] Remove cascading dead code from v1 builder
- ✅ Removed 3 dead functions: `_shadow_probe_nonstandard_constructive()`, `_nonstandard_constructive_v2_policy()`, `_build_constraint_flags_per_seat()`
- ✅ Removed inline PC/OC nudge blocks + nonstandard call site block from v1 builder
- ✅ Removed dead variables: `rs_bucket_snapshot`, `seat_subprofile_stats`, `v2_policy`, RS bucket tracking
- ✅ Removed shadow functions from orchestrator.py + admin menu item 4
- ✅ Removed unused `Mapping` import
- deal_generator.py: 2,241 → 1,896 lines (−345); orchestrator.py: 705 → 524 lines (−181)

### 5. [x] HCP Feasibility Rejection
- ✅ **Batch 1**: `_card_hcp()`, `_deck_hcp_stats()`, `_check_hcp_feasibility()` + 26 unit tests
- ✅ **Batch 2**: HCP check in `_deal_with_help()` + v2 builder attribution handling
- ✅ **Batch 3**: 10 integration tests (gate on/off, rejection/feasible, edge cases)
- ✅ **Batch 4**: Gate flipped to True, Profile E end-to-end tests (7 tests: v2 builder + full pipeline)
- `ENABLE_HCP_FEASIBILITY_CHECK = True` — active in production
- Profile E (6 spades + 10-12 HCP) generates successfully with v2 + HCP rejection

### 6. [x] Profile E viability check fails too early
- ✅ **Resolved**: The "100 attempts" error was v1-only (`MIN_ATTEMPTS_FOR_UNVIABLE_CHECK` in v1 builder). The v2 builder (active since D9) has no early termination — uses full 10,000 attempts.
- ✅ Profile E generates successfully via v2 + shape help + HCP feasibility rejection
- ✅ End-to-end tests prove it: 10 boards via v2 builder, 5 boards via generate_deals() pipeline

### 8. [x] RS-Aware Pre-Selection for v2 Shape Help
- **Problem**: "Defense to 3 Weak 2s" profile failed 100% (0/20 boards, 200,000 attempts). RS constraints invisible to v2 shape help — W needs 6-card suit but `_dispersion_check` and `_pre_allocate` only see standard constraints.
- ✅ **Batch 1**: `_pre_select_rs_suits()` — pre-select RS suit(s) before dealing (10 tests)
- ✅ **Batch 2**: Extended `_dispersion_check()` with RS awareness — RS suits flagged tight (8 tests)
- ✅ **Batch 3**: `_pre_allocate_rs()` — pre-allocate cards for RS pre-selected suits (8 tests)
- ✅ **Batch 4**: Extended `_deal_with_help()` with RS pre-allocation support (6 tests)
- ✅ **Batch 5**: Main wiring — v2 builder calls `_pre_select_rs_suits()`, passes to dispersion/help/matching; `seat_viability.py` extended with optional `pre_selected_suits` params; restructured `_deal_with_help()` to 3-phase (all tight seats pre-allocated, including last seat)
- ✅ **Batch 6**: End-to-end tests — diagnostic + pipeline tests pass
- New test file: `test_rs_pre_selection.py` (32 tests); updated `test_defense_weak2s_diagnostic.py`, `test_hcp_feasibility.py`

### 9. [x] Board-Level Retry + Production Hardening
- **Problem**: "Defense to Weak 2s" passed tests (2/20 boards with known seeds) but crashed in production — `generate_deals()` failed on board 1 after 10,000 attempts.
- ✅ **Board-level retries**: `generate_deals()` retries each board up to `MAX_BOARD_RETRIES = 50` times. Each retry starts from advanced RNG state → different subprofile selections, RS suits, random fills. Total budget per board: 50 × 10,000 = 500,000 attempts.
- ✅ **Subprofile re-rolling**: `SUBPROFILE_REROLL_INTERVAL = 5000` — within each 10K-attempt retry, re-select subprofiles halfway through. Critical for profiles with many subprofile combos (N×E = 16 combos, some much easier than others).
- ✅ **HCP-targeted RS pre-allocation**: `RS_PRE_ALLOCATE_HCP_RETRIES = 10` — retry pre-allocation sampling to find cards whose HCP is on-track for the suit's target range.
- ✅ **Faster RS re-rolling**: `RS_REROLL_INTERVAL` reduced from 2000 to 500.
- **Result**: "Defense to 3 Weak 2s" generates 6 boards in ~50 seconds. Easy profiles still instant.
- deal_generator.py: 2,362 → 2,445 lines (+83); seat_viability.py: 601 lines (unchanged)

---

## Enhancements

### 7. [ ] Refactor large files
- `deal_generator.py` (2,445 lines) — split v1/v2, helpers, HCP feasibility, RS pre-selection, constants into separate modules
- `hand_profile_model.py` (921 lines) — split data models from logic
- `profile_cli.py` (968 lines) — split command handlers
- `orchestrator.py` (524 lines) — split session management from CLI routing

---

## Summary
Architecture: 9 (9 done) | Enhancements: 1 | **Total: 1 pending**

**Tests**: 414 passed, 4 skipped | **Branch**: refactor/deal-generator

---

## Completed (34 items + #5, #6, #8, #9)
<details>
<summary>Click to expand</summary>

- Board-level retry + production hardening (#9): 50 retries per board, subprofile re-roll, HCP-targeted RS pre-alloc — "Defense to Weak 2s" works in production (~50s for 6 boards)
- RS-aware pre-selection (#8): pre-select RS suits before dealing, extend dispersion/help/matching — "Defense to Weak 2s" now viable
- HCP feasibility rejection (#5): `_check_hcp_feasibility()` active, 43 tests, Profile E end-to-end proven
- Profile E viability (#6): resolved — v1-only issue, v2 has no early termination
- Dead code cleanup: removed 5 stubs, 2 flags, 2 hooks, simplified _get_constructive_mode (−161 lines, −25 tests)
- v2 shape-based help system: D0-D9 complete (dispersion check, pre-allocation, deal_with_help, v2 MVP, attribution, benchmarks, swap)
- Magic profile name checks, constraint state to v2, "too hard = unviable" rule
- Subprofile viability tracking, HCP vs shape classification, attribution to policy
- Standard vs nonstandard analysis, default dealing order (Steps 1,3,4,5)
- Latent bugs (3), dead code (10), performance (1), code quality (6), future (3)

</details>
