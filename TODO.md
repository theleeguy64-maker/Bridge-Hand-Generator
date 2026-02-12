# TODOs

## Start Tasks
- [ ] Run profile management in program
- [ ] Review all profiles (check constraints, metadata, dealing order)

---

## Architecture

### 1. [x] Base Smart Hand Order (dead code — remove with v1)
- ✅ `_base_smart_hand_order()` in wizard_flow.py (5-priority algorithm, 56 tests)
- ⚠️ **Dead code, redundant with v2**: Analysis showed v2 handles ordering independently:
  - `_build_processing_order()` handles RS-before-PC/OC matching order
  - `_dispersion_check()` + `_deal_with_help()` handle pre-allocation regardless of dealing order
  - Dealing order's only real v2 effect is "last seat gets remainder" — minimal performance impact
- **Scheduled for removal alongside v1 builder**

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

### 7. [x] Refactor deal_generator.py (Batches 1-5 complete)
- `deal_generator.py` — all 5 batches done
  - ✅ **Batch 1**: `deal_generator_types.py` (262 lines) — types, constants, dataclasses, exception, debug hooks
  - ✅ **Batch 2**: `deal_generator_helpers.py` (447 lines) — viability, HCP, deck, subprofile weights, vulnerability/rotation
  - ✅ **Batch 3**: `deal_generator_v2.py` — 8 v2 shape-help helpers extracted (LOW RISK)
  - ✅ **Batch 4A**: v2 builder moved to `deal_generator_v2.py` (MEDIUM RISK)
  - ✅ **Batch 4B**: `deal_generator_v1.py` (795 lines) — v1 builder + hardest-seat + constructive help extracted with late-import pattern
  - ✅ **Batch 5**: Cleanup facade — removed unused imports, consolidated re-exports, removed stale comments, added module docstring
  - `deal_generator.py`: 2,183 → 398 lines (−1,785); `deal_generator_v1.py`: 795; `deal_generator_v2.py`: 1,113; `_types`: 262; `_helpers`: 452
  - NOTE: `_select_subprofiles_for_board` kept in facade (isinstance monkeypatch sensitivity)
  - NOTE: v1 and v2 both use late import `from . import deal_generator as _dg` for monkeypatchable values
- `hand_profile_model.py` (835 lines) — split data models from logic
- `profile_cli.py` (957 lines) — split command handlers
- `orchestrator.py` (528 lines) — split session management from CLI routing

### 17. [x] Profile Diagnostic Tool (Admin Menu)
- ✅ `profile_diagnostic.py` (209 lines) — generic diagnostic runner for any profile
- ✅ Admin menu item 3 "Profile Diagnostic": choose profile, set board count, run v2 builder with failure attribution
- ✅ Per-board output (shape, HCP, attempts) + aggregate failure attribution table (5 categories x 4 seats)
- ✅ Help text updated in `menu_help.py`

### 18. [x] Wizard refactor (separate IO from logic) — REMOVED
- Removed from backlog — low priority, large effort, not blocking anything

### 13. [x] HCP-aware constrained fill for RS range suits
- ✅ `_constrained_fill()` now accepts optional `rs_suit_hcp_max` parameter — per-suit HCP cap for RS suits
- ✅ `_deal_with_help()` Phase 3 extracts per-suit HCP max from RS constraints via `_resolve_rs_ranges()` and passes to fill
- ✅ Honor cards that would bust the per-suit cap are skipped; spot cards always accepted (0 HCP)
- ✅ 5 unit tests in `test_shape_help_v3.py` (blocks honor, allows spots, backward compat, multi-suit, under-limit)
- **Zero overhead** when `rs_suit_hcp_max=None` (default for non-RS seats)

### 19. [x] Profile management bug fixes (blocking bugs)
- ✅ Added `to_dict()`/`from_dict()` to `SubprofileExclusionData` — profiles with exclusions crashed on load/save
- ✅ Fixed `validate()` bug — `len(seat_profile.subprofiles)` not `len(seat_profiles)`
- ✅ Removed duplicate `SubprofileExclusionClause` — consolidated to single frozen definition
- ✅ Removed dead `_render_full_profile_details_text()` from `profile_cli.py`
- 7 tests added for exclusion serialization round-trips and validation

### 20. [x] Profile store safety (`profile_store.py`)
- ✅ `_load_profiles()` uses `HandProfile.from_dict()` with try/except for `(JSONDecodeError, TypeError, KeyError, ValueError)` — corrupted files skip with warning instead of crashing
- ✅ `_atomic_write()` helper: `tempfile.mkstemp()` + `os.fdopen()` + `os.replace()` — crash-safe writes
- ✅ All 3 write sites use `_atomic_write()`: `_save_profile_to_path()`, `save_profile()`, `autosave_profile_draft()`

### 21. [x] Wizard cleanup (`wizard_flow.py`)
- ✅ Removed 2 dead autosave functions (kept single active `_autosave_profile_draft` at line 1624)
- ✅ Removed dead `_prompt_random_suit_constraint()`, `_default_dealing_order_for_dealer()`
- ✅ Removed dead `_edit_subprofile_exclusions()` (superseded by `_edit_subprofile_exclusions_for_seat()`)
- SuitRange builders (`_build_suit_range_for_prompt` vs `_prompt_suit_range`) both actively used — left as-is
- wizard_flow.py: 1,965 → 1,779 lines (−186)

### 22. [x] Standardize `ns_role_mode` defaults
- ✅ All 8 locations now consistently use `"no_driver_no_index"` as default
- ✅ Dataclass field, `to_dict()`, `from_dict()`, `ns_driver_seat()`, validate, wizard — all aligned

### 23. [x] Profile CLI cleanup (`profile_cli.py`)
- ✅ Removed unused imports (`Any`, `Dict`)
- ✅ Narrowed `except Exception` to `(JSONDecodeError, TypeError, KeyError, ValueError)` in `_load_profiles()`
- ✅ Extracted `_print_profile_metadata()` + `_print_profile_constraints()` — eliminates duplicate metadata printing
- ✅ `draft_tools_action()` duplicate already removed in prior work

### 24. [x] Duplicate definitions in `hand_profile_model.py`
- ✅ Already resolved — duplicate `SubProfile` and orphaned `from_dict()` were cleaned up in #19
- ✅ Removed duplicate unreachable `return None` in `ns_driver_seat()`

### 25. [x] Stale code in `orchestrator.py`
- ✅ Simplified `_run_profile_management()` — removed unreachable hasattr fallback chain and error path

### 26. [x] Profile wizard facade cleanup (`profile_wizard.py`)
- ✅ Removed unused imports (`Path`, `replace`)
- ✅ Removed duplicate `clear_screen` import (was imported from both `cli_io` and `wizard_io`)
- ✅ Narrowed `except Exception` to `except ImportError` on optional helper imports

### 27. [x] Profile store minor cleanup (`profile_store.py`)
- ✅ Consistent trailing `"\n"` on all JSON writes (all 3 write sites)
- ✅ Narrowed `except Exception` to `except OSError` in `delete_draft_for_canonical()`

### 28. [x] Remove stale TODO comments in code
- ✅ Removed `(TODO #5)` from headers in `deal_generator_v2.py` and `deal_generator_types.py`

### 29. [x] Code Review Cleanup
- ✅ **Batch 1 — Bug fixes**: Fixed PC constraint AttributeError in `wizard_flow.py`; replaced stale `ns_index_coupling_enabled` with `ns_role_mode`-derived logic in `deal_generator.py` + `profile_viability.py`
- ✅ **Batch 2 — Dead code**: Removed unused `Sequence`/`Set` imports, dead `DEBUG_SECTION_C`, dead `_pw()`
- ✅ **Batch 3 — Inconsistencies**: Standardized `profile_store.py` strip/get patterns; fixed `Dict[str, object]` → `Dict[str, SuitRange]`; fixed profile JSON typos
- ✅ **Batch 4 — Magic numbers**: Added 5 named constants (`FULL_DECK_HCP_SUM`, `FULL_DECK_HCP_SUM_SQ`, `MAX_HAND_HCP`, `UNVIABLE_MIN_FAILS`, `UNVIABLE_MIN_RATE`)
- ✅ **Batch 5 — Clarification**: Added HCP attribution imprecision comment in v2 builder
- ✅ **Additional bugs**: Fixed `rotate_flag` NameError in `create_profile_interactive()`; fixed `constraints_mode` TypeError in `profile_wizard.py`; added `decimal_places` param to `_input_float_with_default()`
- ✅ **Final cleanup**: Removed dead `_HCP_BY_RANK`, dead `allow_std_constructive` assignments in v1, malformed comment, redundant `zip(strict=False)`, redundant lazy import
- ✅ **Second pass**: Fixed `save_as_new_version_action()` missing 5 metadata fields; fixed `PartnerContingentConstraint` → `PartnerContingentData` NameError; removed dead `safe_input_int_with_default`; fixed `lin_encoder.py` fallback vulnerability code `'x'` → `'0'`
- ✅ **Third pass (deep dive)**: Fixed `sub_profiles` → `subprofiles` attribute name (wizard_flow.py + tests); added `is_invariants_safety_profile`/`use_rs_w_only_path` to `to_dict()`; fixed extra space in text_output.py f-string; removed dead `_admin_menu()`/`_deal_management_menu()` + unused import from orchestrator.py

### 30. [x] Profile Management Test Coverage
- ✅ Fixed `edit_profile_action()` metadata-only path missing 3 fields (`subprofile_exclusions`, `is_invariants_safety_profile`, `use_rs_w_only_path`)
- ✅ `test_profile_mgmt_actions.py` (9 tests): edit metadata/constraints/cancel, delete confirm/cancel, save-as-new-version, draft tools (no drafts, delete one, delete all)
- ✅ `test_profile_mgmt_menus.py` (4 tests): run_profile_manager dispatch + error recovery, admin_menu dispatch + exit
- ✅ `test_wizard_edit_flow.py` (5 tests): skip-all preserves profile, edit-one-seat, autosave trigger, constraints roundtrip, exclusion editing

### 31. [x] Custom Profile Display Order (`sort_order`)
- ✅ Added `sort_order: Optional[int] = None` to HandProfile (model + serialization)
- ✅ `build_profile_display_map()` in profile_store.py — shared helper for non-sequential numbering
- ✅ Updated profile_cli.py (`_choose_profile`, `list_profiles_action`) + orchestrator.py (`_choose_profile_for_session`)
- ✅ Preserved `sort_order` in metadata edit + save-as-new-version
- ✅ Profile A-E Test files set to sort_order 20-24

### 32. [x] Code Simplification
- ✅ Removed ~20 redundant `getattr()` calls on dataclass fields across hand_profile_model.py, profile_cli.py, orchestrator.py
- ✅ Extracted `print_profile_display_map()` in profile_store.py — replaces 3 duplicate display loops
- ✅ Deduplicated filename construction in profile_store.py — `autosave_profile_draft_for_new()` reuses `_profile_path_for()`
- ✅ Removed dead `_run_profile_management()` wrapper from orchestrator.py
- Skipped `_safe_file_stem` → `_slugify` consolidation — `&` in profile names produces different output, would break existing file paths

### 33. [x] Deep Code Review Cleanup
- ✅ **Bug fix**: `deal_output.py:314` — `_convert_to_lin_deals()` result was discarded; LIN files now get proper vulnerability data
- ✅ **Dead code**: Removed `_build_deck()` from `seat_viability.py` (duplicate of `deal_generator_helpers.py`)
- ✅ **Dead code**: Removed `_input_choice()` + unused `Sequence`/`TypeVar` imports from `cli_io.py`; updated `test_cli_io.py`
- ✅ **Dead module**: Deleted `text_output.py` + `test_text_output.py` (superseded by `deal_output.py`)
- ✅ **Consistency**: Standardized `sort_keys=True` in all 4 JSON save sites (`profile_cli.py`, `profile_store.py` ×3)
- ✅ **Docstring**: Fixed `hand_profile_validate.py` — docstring said `"north_drives"` default but code uses `"no_driver_no_index"`
- ✅ **Typo**: Fixed `wizard_flow.py` comment — `_build_Opponent seat_profile` → `_build_seat_profile`; removed stale `_input_choice` reference

### 34. [x] Complexity Reduction Refactoring (R6-R14)
- ✅ **R6**: Extracted `_validate_for_session()` + `_print_session_summary()` from orchestrator session flow; reused in diagnostic
- ✅ **R7**: Generic `_run_menu_loop()` replaces duplicate `main_menu()`/`admin_menu()` while-loops
- ✅ **R8**: Extracted `_check_suit_range()` helper in `seat_viability.py` — deduplicates PC/OC matching
- ✅ **R12**: Extracted `WE_COLUMN_WIDTH = 28` constant in `deal_output.py`
- ✅ **R13**: Consolidated 4 regex patterns at module top in `lin_tools.py`; removed duplicate `_BOARD_LABEL_RE`
- ✅ **R14**: Deduplicated seed logic in `setup_env.py` (2 identical branches → 1)
- Skipped R9 (suit dict factory — hot-path overhead), R10 (depends on R1), R11 (`show_range_suffix` is a legitimate feature with 20+ callers)

### 35. [x] Code Review (#35) — 6 fixes
- ✅ **A1**: `failure_report.py` now uses v2 builder (`_build_single_constrained_deal_v2`) — was using v1, attribution results mismatched production
- ✅ **B1**: `profile_cli.py` `_save_profile_to_path()` now uses atomic writes (tempfile + `os.replace`) — was using bare `json.dump`, crash-unsafe
- ✅ **A2**: Removed dead `_create_profile_from_base_template()` from `profile_cli.py` — had latent `.profile` bug on tuple
- ✅ **B2**: Added missing `import random` to `seat_viability.py` — 4 type annotations used `random.Random` without import
- ✅ **C1**: Fixed stale comment on `PRE_ALLOCATE_FRACTION` — said "50%" but value is 0.75
- ✅ **C2**: Deduplicated `TOTAL_DECK_HCP` in `profile_viability.py` — now imports `FULL_DECK_HCP_SUM` from `deal_generator_types`

### 37. [x] Auto-Compute Dealing Order (least constrained last)
- ✅ `_compute_dealing_order()` in `deal_generator_v2.py` — computes optimal dealing order from chosen subprofiles
- ✅ Risk scoring: RS=1.0, PC/OC=0.5, standard=0.0; HCP range + clockwise tiebreakers
- ✅ Least constrained seat always last (gets v2 remainder advantage)
- ✅ Recomputed on each subprofile re-roll (adapts per board)
- ✅ Removed dealing order prompts from wizard (`_build_profile`, `create_profile_interactive`)
- ✅ Removed dealing order editing from `edit_profile_action()` metadata mode
- ✅ Relaxed dealer-first validation in `hand_profile_model.py`
- ✅ 9 tests for `_compute_dealing_order()` + `_subprofile_constraint_type()`
- **Result**: Defense Weak 2s **2.7x faster** (52ms → 19.5ms avg), Our 1 Major **1.5x faster**

### 38. [x] Code Review (#38) — 8 fixes
- ✅ **A1**: Fixed stale "dealer must be first" docstring in `hand_profile_model.py`
- ✅ **A2**: Fixed debug hook signature comment — added `seat_fail_hcp`, `seat_fail_shape` params
- ✅ **A3**: Consistent unconstrained HCP default — `40` → `MAX_HAND_HCP` in constrained fill
- ✅ **B1**: Removed dead `_suggest_dealing_order()` from `wizard_flow.py` (66 lines)
- ✅ **B2**: Removed dead `_parse_hand_dealing_order()` from `profile_cli.py` (23 lines)
- ✅ **B3**: Removed unused `hand_dealing_order` param from `_edit_subprofile_exclusions_for_seat()`
- ✅ **B4**: Consolidated `PROFILE_DIR_NAME` — profile_cli + orchestrator import from profile_store
- ✅ **C2**: `_default_clockwise_order_starting_with()` now delegates to `_default_dealing_order()`

### 36. [x] v1 vs v2 Review + Debug Hook Fix
- ✅ Comprehensive review of `deal_generator_v1.py` (790 lines) vs `deal_generator_v2.py` (1,122 lines)
- **Conclusion**: v2 is a complete successor — every v1 feature was replaced with a superior mechanism or deliberately removed
- v1 features deliberately absent from v2 (by design):
  - Constructive help → replaced by shape-based pre-allocation
  - Hardest-seat selection → replaced by proactive dispersion checking
  - Per-attempt subprofile re-selection → replaced by periodic re-rolling intervals
  - Early unviable termination (`MIN_ATTEMPTS_FOR_UNVIABLE_CHECK`) → removed to avoid false positives; board-level retry handles this
- ✅ **Fix**: v2 `_DEBUG_ON_MAX_ATTEMPTS` hook now passes real `viability_summary` (was passing `None`)
  - Added `_compute_viability_summary` import to `deal_generator_v2.py`
  - Updated test assertion in `test_shape_help_v3.py`

---

## Benchmark Portfolio

5 profiles spanning trivial → hardest. Run via `benchmark_portfolio.py [num_boards]`.

| # | Profile | Difficulty | Key Constraint |
|---|---------|-----------|----------------|
| 1 | Profile A (Loose) | Trivial | No constraints (baseline) |
| 2 | Profile D (Suit+Pts) | Moderate | N: 5-6 spades + 10-12 HCP |
| 3 | Profile E (Suit+Pts+) | Hard | N: exactly 6 spades + 10-12 HCP |
| 4 | Our 1 Major & Interference | Hard | All 4 seats: RS+PC+OC, 3 E subs |
| 5 | Defense to 3 Weak 2s | Hardest | 16 sub combos, OC+RS mixing |

**Baseline (20 boards, seed=778899) — with auto-compute dealing order (#37):**

| Profile | Wall(s) | Avg(ms) | Med(ms) | P95(ms) | Max(ms) |
|---------|---------|---------|---------|---------|---------|
| Profile A | 0.001 | 0.0 | 0.0 | 0.1 | 0.1 |
| Profile D | 0.002 | 0.1 | 0.1 | 0.3 | 0.3 |
| Profile E | 0.002 | 0.1 | 0.1 | 0.2 | 0.2 |
| Our 1 Major | 0.044 | 2.2 | 0.5 | 9.4 | 9.4 |
| Defense Weak 2s | 0.384 | 19.2 | 11.5 | 78.0 | 78.0 |
| **TOTAL** | **0.433** | | | | |

---

## Summary
Architecture: 15 (15 done) | Enhancements: 22 (22 done) | **All complete**

**Tests**: 489 passed, 4 skipped | **Branch**: refactor/deal-generator

**Admin menu**: 0-Exit, 1-LIN Combiner, 2-Draft Tools, 3-Profile Diagnostic, 4-Help

---

## Completed (37 items + #5, #6, #8, #9, #10, #11, #12, #13, #14, #15, #16, #17, #19, #35)
<details>
<summary>Click to expand</summary>

- Code review cleanup (#29): 6 bug fixes (PC constraint AttributeError, stale ns_index_coupling_enabled, rotate_flag NameError, constraints_mode TypeError, decimal_places TypeError, HCP attribution comment), dead code removal (_HCP_BY_RANK, DEBUG_SECTION_C, _pw(), allow_std_constructive), inconsistency fixes (strip patterns, type annotations, profile JSON typos), 5 named constants replacing magic numbers
- Profile store safety (#20): `_load_profiles()` error handling + `_atomic_write()` for crash-safe writes on all 3 write sites
- Profile store cleanup (#27): consistent trailing newline + narrowed `except OSError`
- Wizard cleanup (#21): removed 5 dead functions from wizard_flow.py (−186 lines)
- Profile management bug fixes (#19): SubprofileExclusionData serialization, validate() fix, duplicate class removal, dead function removal. 7 tests.
- HCP-aware constrained fill (#13): per-suit HCP max enforcement in _constrained_fill() for RS range suits. 5 tests.
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
