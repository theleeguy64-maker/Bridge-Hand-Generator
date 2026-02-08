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
- ✅ `_pre_allocate()` — 75% of suit minima (D4)
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
- ✅ **Subprofile re-rolling**: `SUBPROFILE_REROLL_INTERVAL = 1000` — within each 10K-attempt retry, re-select subprofiles to try different N/E combos. Critical for profiles with many subprofile combos (N×E = 16 combos, some much easier than others).
- ✅ **HCP-targeted RS pre-allocation**: `RS_PRE_ALLOCATE_HCP_RETRIES = 10` — retry pre-allocation sampling to find cards whose HCP is on-track for the suit's target range.
- ✅ **Faster RS re-rolling**: `RS_REROLL_INTERVAL` reduced from 2000 to 500.
- **Result**: "Defense to 3 Weak 2s" generates 6 boards in ~50 seconds. Easy profiles still instant.
- deal_generator.py: 2,362 → 2,445 lines (+83); seat_viability.py: 601 lines (unchanged)

### 10. [x] Performance Optimizations (#2-#8)
- ✅ **#2 Early total-HCP pre-check**: Quick HCP sum check before `_match_seat()` in v2 builder — rejects impossible hands without full matching
- ✅ **#3 Reduce SUBPROFILE_REROLL_INTERVAL**: 5000 → 1000 for faster subprofile cycling
- ✅ **#4 Pre-build master deck constant**: `_MASTER_DECK` module-level list avoids 52 string concatenations per attempt
- ✅ **#5 Index-based dealing**: `deck[:take]` + `del deck[:take]` instead of `rng.sample()` + set-filter (deck already shuffled)
- ✅ **#6 Pre-index deck by suit**: Build `{suit: [cards]}` dict once per pre-allocation call in `_pre_allocate()` and `_pre_allocate_rs()`, remove all chosen cards in one pass
- ✅ **#7 Incremental HCP tracking**: Full deck always has hcp_sum=40, hcp_sum_sq=120; subtract pre-allocated cards' contributions instead of scanning remaining deck
- ✅ **#8 Unroll `_match_standard` suit loop**: Direct attribute access instead of constructing `[("S", std.spades), ...]` list on every call (hot path)
- **Result**: Test suite ~37s → ~30s (~19% faster). Production generation also faster.
- deal_generator.py: 2,445 → 2,530 lines (+85); seat_viability.py: 601 → 615 lines (+14); orchestrator.py: 524 → 528 lines (+4)

### 11. [x] Constrained Fill + PRE_ALLOCATE_FRACTION 0.75
- ✅ **PRE_ALLOCATE_FRACTION 0.50 → 0.75**: More aggressive pre-allocation gives tight seats a bigger head start. "Defense to Weak 2s" success rate 6/50 → 22/50 boards per 10K attempts.
- ✅ **Constrained fill — suit max enforcement**: `_constrained_fill()` walks the shuffled deck and skips cards that would bust a suit's max_cards. Eliminated 100% of W shape failures (27K → 0).
- ✅ **Constrained fill — HCP max enforcement**: Also skips honor cards (A/K/Q/J) that would push total HCP over the seat's total_max_hcp. Reduced W HCP failures 81% (155K → 29K).
- ✅ **`_get_suit_maxima()`**: Extracts effective per-suit max_cards from standard + RS constraints (respects pair_overrides).
- **Result**: "Defense to Weak 2s" per-board success rate ~3.7x better. W shape failures eliminated, W HCP failures reduced 81%.
- deal_generator.py: 2,530 → 2,678 lines (+148)

### 12. [x] Adaptive Re-Seeding + Per-Board Timing
- ✅ `RESEED_TIME_THRESHOLD_SECONDS = 1.75` — per-board wall-clock budget before re-seeding (tightened from 3.0; bad seed 101: 22s→6.8s = 3.2x speedup)
- ✅ `generate_deals()` tracks per-board elapsed time; on timeout, replaces RNG with fresh `SystemRandom` seed
- ✅ `DealSet` extended with `board_times: List[float]` and `reseed_count: int`
- ✅ Session summary shows avg/max per board time + re-seed count
- **Motivation**: "Defense to Weak 2s" showed 6x time variance depending on seed (2.9s vs 17.2s for 6 boards)

### 15. [x] Hot-Path Micro-Optimizations (_CARD_HCP + setdefault elimination)
- ✅ **`_CARD_HCP` dict**: Pre-built 52-card HCP lookup in `deal_generator_types.py` — eliminates `_card_hcp()` function-call overhead on 4.5M+ calls/run. 6 hot-path call sites use `_CARD_HCP[c]` directly; `_card_hcp()` retained for external/test callers.
- ✅ **Pre-initialized suit dicts**: `_pre_allocate()` and `_pre_allocate_rs()` use `{"S": [], "H": [], "D": [], "C": []}` instead of `setdefault()` — eliminates 7.4M `setdefault` calls.
- **Result**: 250-board Weak 2s benchmark 20.52s → 17.46s (**15% faster**), function calls 57.8M → 41.4M (**−28%**). Test suite 4.04s → 3.61s (**−11%**).

### 14. [x] Full RS Pre-Allocation (RS_PRE_ALLOCATE_FRACTION = 1.0)
- ✅ `RS_PRE_ALLOCATE_FRACTION = 1.0` — pre-allocate 100% of RS suit min_cards with HCP targeting (separate from standard `PRE_ALLOCATE_FRACTION = 0.75`)
- **Root cause**: With 0.75 fraction, W pre-allocated 4 of 6 RS cards; remaining 2 came from random fill blind to RS suit HCP window (5-7). This caused 89% of all W failures (71% of total failures).
- **Result**: "Defense to Weak 2s" default seed 7.5s → 1.5s (**5x**), bad seed 22s → 1.1s (**20x**). Diagnostic: 8/20 → 20/20 boards, W failures 71% → 2.5%.
- **Limitation**: For RS with card range (e.g. 6-7), fill can still add a card beyond min_cards without HCP awareness. Not an issue for current profiles (W has min=max=6). See #13.

### 16. [x] Cross-Seat HCP & Card-Count Feasibility Checks
- **Problem**: "Defense to 3 Weak 2s" has 43.8% of N×E subprofile combos mathematically impossible (sum(min_hcp) > 40). Each impossible combo burns 1,000 attempts before re-rolling.
- ✅ **Batch 1**: Core `_cross_seat_feasible()` function + 4 accessor helpers in `profile_viability.py` (21 tests)
- ✅ **Batch 2**: Dead subprofile detection at validation time — `_check_cross_seat_subprofile_viability()` warns for dead subs, raises `ProfileError` if ALL subs on any seat are dead. Wired into `validate_profile_viability()` step 3. `hand_profile_validate.py` step 9 upgraded to extended validation. (10 tests)
- ✅ **Batch 3**: Runtime feasibility retry in `_select_subprofiles_for_board()` — retries up to `MAX_SUBPROFILE_FEASIBILITY_RETRIES=100` times on infeasible combos. Dead N sub0 and E sub0 never selected. (6 tests)
- ✅ **Batch 4**: Integration + benchmark — 20 boards Weak 2s end-to-end, selection comparison (2 tests)
- **Result**: 0% infeasible subprofile selections (was 43.8%). Dead subs (N sub1, E sub1) eliminated at both validation and runtime. Zero overhead for fully-feasible profiles.
- New test file: `test_cross_seat_feasibility.py` (39 tests)

---

## Enhancements

### 7. [ ] Refactor large files
- `deal_generator.py` — Batches 1-4A done, Batches 4B+5 pending (v1 extraction, cleanup)
  - ✅ **Batch 1**: `deal_generator_types.py` (262 lines) — types, constants, dataclasses, exception, debug hooks
  - ✅ **Batch 2**: `deal_generator_helpers.py` (447 lines) — viability, HCP, deck, subprofile weights, vulnerability/rotation
  - ✅ **Batch 3**: `deal_generator_v2.py` — 8 v2 shape-help helpers extracted (LOW RISK)
  - ✅ **Batch 4A**: v2 builder moved to `deal_generator_v2.py` (MEDIUM RISK)
  - [ ] **Batch 4B**: `deal_generator_v1.py` — v1 builder + hardest-seat + constructive help (HIGH RISK, late-import pattern)
  - [ ] **Batch 5**: Cleanup facade, verify, update docs
  - `deal_generator.py`: 2,183 → 1,158 lines (−1,025); `deal_generator_v2.py`: 1,087 lines
  - NOTE: `_select_subprofiles_for_board` kept in facade (isinstance monkeypatch sensitivity)
  - NOTE: v2 uses late import `from . import deal_generator as _dg` for monkeypatchable values
- `hand_profile_model.py` (921 lines) — split data models from logic
- `profile_cli.py` (968 lines) — split command handlers
- `orchestrator.py` (528 lines) — split session management from CLI routing

### 17. [x] Profile Diagnostic Tool (Admin Menu)
- ✅ `profile_diagnostic.py` (209 lines) — generic diagnostic runner for any profile
- ✅ Admin menu item 3 "Profile Diagnostic": choose profile, set board count, run v2 builder with failure attribution
- ✅ Per-board output (shape, HCP, attempts) + aggregate failure attribution table (5 categories x 4 seats)
- ✅ Help text updated in `menu_help.py`

### 13. [ ] HCP-aware constrained fill for RS range suits
- When RS constraint allows a range (e.g. 6-7 cards), pre-allocation covers min_cards (6) with HCP targeting, but constrained fill can blindly add a 7th card that busts the RS suit HCP window
- **Current impact**: None for "Defense to Weak 2s" (W has min=max=6). Theoretical concern for N/E subprofiles with 5-6 or 6-7 card RS ranges
- **Options**: (a) cap fill at min_cards for RS suits (never add beyond pre-allocated), (b) make fill HCP-aware for RS suits
- **Priority**: Low — only matters if future profiles have RS range + tight suit HCP

---

## Summary
Architecture: 15 (15 done) | Enhancements: 3 (1 done) | **Total: 2 pending**

**Tests**: 453 passed, 4 skipped | **Branch**: refactor/deal-generator

**Admin menu**: 0-Exit, 1-LIN Combiner, 2-Draft Tools, 3-Profile Diagnostic, 4-Help

---

## Completed (34 items + #5, #6, #8, #9, #10, #11, #12, #14, #15, #16, #17)
<details>
<summary>Click to expand</summary>

- Profile Diagnostic tool (#17): generic diagnostic runner in Admin menu — pick any profile, run v2 builder with failure attribution, see per-board results + aggregate summary
- Cross-seat feasibility checks (#16): `_cross_seat_feasible()` rejects impossible subprofile combos at both validation time (dead sub detection) and runtime (selection retry). Eliminates 43.8% wasted attempts on Weak 2s profile. 39 tests.
- Hot-path micro-optimizations (#15): _CARD_HCP pre-built dict + pre-initialized suit dicts — eliminates 4.5M function calls + 7.4M setdefault calls. Weak 2s 250-board benchmark 20.52s→17.46s (15% faster)
- Full RS pre-allocation (#14): RS_PRE_ALLOCATE_FRACTION=1.0 — pre-allocate all RS min_cards with HCP targeting. "Defense to Weak 2s" default seed 7.5s→1.5s (5x), bad seed 22s→1.1s (20x)
- Adaptive re-seeding (#12): per-board timing + automatic re-seed on slow boards (1.75s threshold) — eliminates seed-dependent variance
- Constrained fill + 0.75 fraction (#11): suit max + HCP max enforcement during fill, PRE_ALLOCATE_FRACTION 0.50→0.75 — W shape failures eliminated, HCP failures −81%
- Performance optimizations (#10): early HCP pre-check, master deck constant, index-based dealing, suit pre-indexing, incremental HCP tracking, unrolled _match_standard (~19% faster)
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
