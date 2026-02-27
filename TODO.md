# TODOs

## Start Tasks
- [x] Run profile management in program
- [ ] Review all profiles (check constraints, metadata, dealing order)

## Recent Fixes (#68, #42-#45)
- [x] Category display: indent profiles under headers, remove test sort_order 20-24
- [x] Code review #68: A1/A2 — PC/OC validation uses RS check instead of stale hand_dealing_order; C2 — standardize _input_int keyword-only args; C3 — fix stale comment in deal_generator_v2.py; D1 — remove redundant isinstance in _try_pair_coupling; D3 — clarify failure_report.py board loop

## Older Fixes (#42, #43, #44, #45)
- [x] Fix prompt_int argument order bug in _prompt_suit_range (OC/PC suit range prompts showed inverted bounds)
- [x] Profile Summary: move File to last, rename to "File name", show filename only
- [x] Version change in metadata edit now saves to new file (keeps old version)
- [x] Add delete_draft_for_canonical to constraints-only edit and save-as-new-version paths
- [x] New profile: Opps_Open_&_Our_TO_Dbl_Balancing_v0.1
- [x] Exclusions: numbered menu (0 Exit, 1 Shapes, 2 Rule, 3 Help) replaces text prompt (#43)
- [x] Code review #44: 7 fixes (misleading save msg, dead _build_exclusion_shapes, stale comment, 5 menu tests, draft stub, admin help option 2, unused imports)
- [x] Code review #45: circular import fix, duplicate wrapper removed, empty-rows guard, dead import, stale docstring, debug hook warnings

---

## Architecture

### 1. [x] Base Smart Hand Order (removed)
- ✅ `_base_smart_hand_order()` and 6 helpers removed from wizard_flow.py (−257 lines)
- ✅ `test_default_dealing_order.py` deleted (56 tests for dead code)
- Was redundant with v2's `_compute_dealing_order()` + `_dispersion_check()`

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

### 39. [x] Simplify deal_generator.py facade
- ✅ **Trimmed re-imports**: Explicit re-import lists now only contain `_`-prefixed names (wildcard handles the rest)
- ✅ **Extracted `_try_pair_coupling()`**: Deduplicated NS/EW coupling logic into shared helper (−30 lines)
- ✅ **Cleaned up `generate_deals()`**: Removed stale "C1/C2" docstring, removed "P1.1" comment, removed redundant `continue`
- `deal_generator.py`: 403 → 374 lines (−29)

### 40. [x] Code Review (#40) — 17 fixes
- ✅ **A1**: Fixed misleading "NS role mode set to Any" → `no_driver_no_index` in `profile_cli.py`
- ✅ **A2**: Removed unreachable dead guard (`if seen <= 0`) in `deal_generator_v1.py`
- ✅ **A3**: Fixed `Dict[str, object]` → `Dict[str, SuitRange]` return type in `deal_generator_v2.py`
- ✅ **B1**: Removed SHDO dead code (~250 lines from `wizard_flow.py`) + `test_default_dealing_order.py` (56 tests)
- ✅ **B2-B5**: Removed 4 unused imports (`dataclass`, `_MASTER_DECK`, `asdict`, `profile_wizard`)
- ✅ **B6**: Replaced stale "old line 1201" comment in `deal_generator_v1.py`
- ✅ **C1**: Standardized `tuple`/`dict` → `Tuple`/`Dict` type hints across 4 files
- ✅ **C4**: Replaced duplicate `HCP_MAP` with `_CARD_HCP` in `seat_viability.py`
- ✅ **C5**: Removed trivial `_print_full_profile_details` wrapper in `profile_cli.py`
- ✅ **C7**: Replaced emoji with "WARNING:" text in `wizard_flow.py`
- ✅ **D1**: Simplified hook restoration in `failure_report.py`
- ✅ **D2**: Narrowed `except Exception` to `(ProfileError, ValueError, TypeError)` in `seat_viability.py`
- ✅ **D4**: Simplified `_default_clockwise_order_starting_with()` wrapper in `profile_cli.py`
- Skipped C2/C3 (diverged semantics, `&` in filenames) and D3 (v1 dependency)
- wizard_flow.py: 1,667 → 1,410 lines (−257); seat_viability.py: 598 → 596; profile_cli.py: 889 → 881

### 41. [x] Install mypy + fix all type errors (48 → 0)
- ✅ Installed mypy; initial run found 48 errors across 11 files
- ✅ Fixed all 48 errors across 10 files (30 source files checked, 0 errors)
- Key fixes: missing imports (`random`, `Seat`, `Sequence`), `object` → proper types (`RandomSuitConstraintData`, `SeatProfile`, `SuitRange`), `Optional` annotations for nullable variables, `object.__setattr__` for frozen dataclass writes, `isinstance` guard for dict fallback, removed stale import shadowing
- Used `# type: ignore[no-redef]` for intentional variable reuse across code branches
- Run: `.venv/bin/mypy bridge_engine/ --ignore-missing-imports`

### 44. [x] Code Review #54 — 10 fixes across 11 files
- ✅ **A1 (bug)**: Fixed `failure_report.py` — `total_attempts` under-counted on successful boards (missing +1 for the succeeding attempt that doesn't trigger the hook)
- ✅ **B1 (dead code)**: Removed unreachable `ns_role_for_seat` legacy fallback path in `hand_profile_model.py` `ns_role_buckets()` — `ns_role_usage` is a declared field, `getattr` never returns `None`
- ✅ **B2 (dead code)**: Removed dead `standard_constraints` fallback in `hand_profile_validate.py` — field is named `standard`
- ✅ **C1 (consistency)**: Removed stale `random.seed()` global side effect from `setup_env.py` — `generate_deals()` uses its own `random.Random(setup.seed)`
- ✅ **C5 (consistency)**: Added missing `from __future__ import annotations` to `profile_convert.py` (only file without it)
- ✅ **D1-D5 (simplification)**: Removed ~15 redundant `getattr` calls on known dataclass fields across `hand_profile_validate.py`, `lin_encoder.py`, `orchestrator.py`, `profile_diagnostic.py`, `profile_store.py`; updated test `DummyProfile` stubs
- Skipped: B3 (dual creation paths), C2/C3 (duplicate helpers — diverged semantics), C4 (`Seat` alias — 6 files)
- Also includes: `os.system("clear")` → `subprocess.run(["clear"])` (bandit B605 fix), removed dead `inner_indent` param from `deal_output.py`, upgraded 4 vulnerable deps (cryptography, pip, protobuf, pyasn1)

### 43. [x] Code Review #53 — 7 fixes across 5 files
- ✅ **A1 (bug)**: Fixed `failure_report.py` — `total_attempts` overwritten on each hook call instead of accumulated per board; now uses `latest_attempt_count` pattern matching other counters
- ✅ **B1-B3 (dead code)**: Removed unused `import re` and `Iterable` from `cli_prompts.py`; removed unused `Iterable` from `wizard_flow.py`
- ✅ **C1 (consistency)**: Narrowed `except Exception` → `except OSError` in `setup_env.py` subdirectory creation (matching parent dir pattern)
- ✅ **C2-C3 (consistency)**: Removed 5 redundant `getattr` calls on typed `HandProfile`/`Deal` attributes in `deal_output.py`; updated `DummyProfile` test stub with required attributes

### 42. [x] Code Reviews #51-#52 — ~25 fixes across 16 files
- ✅ **A-severity (bug)**: Fixed `failure_report.py` — v2 builder raises `DealGenerationError` on failure, but code checked `result is None`; now uses try/except
- ✅ **B-severity (dead code)**: Deleted `wizard_constants.py` (single constant), deleted `profile_print.py` (empty stub), removed dead `_match_random_suit()` wrapper from `seat_viability.py`, removed dead `prompt_text()` from `cli_prompts.py`, removed dead `prompt_text` import + `SUITS` import + `sub_kwargs` dict from `wizard_flow.py`, removed unused `SUITS` constant from `profile_cli.py`, removed unused `asdict` import from `hand_profile_validate.py`
- ✅ **C-severity (consistency)**: Standardized 14 lowercase type hints (`list[str]`→`List[str]`, `dict`→`Dict`, `tuple`→`Tuple`, `set`→`Set`) across 8 files; narrowed `except Exception` → `except OSError` in `setup_env.py` (2 locations); narrowed `except Exception` → `except ImportError` in `wizard_flow.py`; removed 4 redundant `hasattr(x, "to_dict")` guards in `hand_profile_validate.py` + `profile_store.py`; removed emoji from `profile_wizard.py` comment
- ✅ **D-severity (simplification)**: Replaced 2 `object.__setattr__` with `dataclasses.replace()` in `wizard_flow.py`; simplified 3 redundant `getattr(profile, "ns_role_mode", ...)` patterns; added type hints to `_pw_attr()`
- Skipped: v1 dead code items (preserved for rollback)

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

**Baseline (20 boards, seed=778899) — with v0.3 Weak 2s profile:**

| Profile | Wall(s) | Avg(ms) | Med(ms) | P95(ms) | Max(ms) |
|---------|---------|---------|---------|---------|---------|
| Profile A | 0.001 | 0.0 | 0.0 | 0.1 | 0.1 |
| Profile D | 0.002 | 0.1 | 0.1 | 0.3 | 0.3 |
| Profile E | 0.002 | 0.1 | 0.1 | 0.2 | 0.2 |
| Our 1 Major | 0.044 | 2.2 | 0.5 | 9.3 | 9.3 |
| Defense Weak 2s | 0.298 | 14.9 | 2.8 | 77.1 | 77.1 |
| **TOTAL** | **0.348** | | | | |

### 45. [x] OC Non-Chosen Suit Support
- ✅ Added `use_non_chosen_suit: bool = False` to `OpponentContingentSuitData` (model + serialization + backward compat)
- ✅ `_compute_rs_allowed_suits()` helper extracts allowed_suits per RS seat
- ✅ `rs_allowed_suits` threaded through `_match_seat` → `_match_subprofile` (optional param, zero overhead when unused)
- ✅ OC matching branch extended: when flag is True, computes `non_chosen = allowed - chosen` and targets inverse suit
- ✅ Wizard prompt: "Target opponent's NON-CHOSEN suit (inverse)?"
- ✅ Validation: rejects profiles where opponent RS doesn't have exactly 1 non-chosen suit (multi-suit non-chosen not yet supported)
- ✅ 25 tests in `test_oc_non_chosen_suit.py` (data model, helper, matching, regression, graceful fail, validation incl. multi-non-chosen rejection, integration, edge cases)
- **Use case**: West RS picks 1 from [S, H]; North OC non-chosen gets the other suit (5-6 cards, 2-7 HCP)

### 46. [x] Code Review #55 — 5 fixes across 4 files
- ✅ **B1**: Removed duplicate `_yes_no()` from `orchestrator.py` (22 lines) — already imported from `cli_io`
- ✅ **C1**: Removed 8 redundant `getattr` calls on typed dataclass fields in `seat_viability.py` `_is_excluded_for_seat_subprofile()`
- ✅ **C2**: Removed 2 unnecessary `# type: ignore[attr-defined]` comments on `SuitRange` attributes in `seat_viability.py`
- ✅ **D1**: Simplified `_fmt_suits()` in `profile_cli.py` — removed redundant `isinstance` branch (both branches did `list(suits)`)
- ✅ **D2**: Narrowed `except Exception` → `except (ImportError, OSError, TypeError, ValueError)` in `wizard_flow.py` `_autosave_profile_draft()`

### 47. [x] PC Non-Chosen Suit Support (inverse PC)
- ✅ Added `use_non_chosen_suit: bool = False` to `PartnerContingentData` (model + serialization + backward compat)
- ✅ `_match_partner_contingent()` extended: computes `non_chosen = allowed - chosen` when flag is True
- ✅ `rs_allowed_suits` passed through to PC matching call site
- ✅ Wizard prompt: "Target partner's NON-CHOSEN suit (inverse)?" + menu label `(chosen or inverse)`
- ✅ Validation: rejects profiles where partner RS doesn't have exactly 1 non-chosen suit
- ✅ 18 tests in `test_pc_non_chosen_suit.py` (data model, matching, regression, graceful fail, validation, integration)
- **Use case**: N RS picks 1 from [S, H]; S PC non-chosen gets the other suit (3-5 cards)

### 48. [x] Code Review #56 — 4 fixes across 4 files
- ✅ **C1**: Removed 2 redundant `getattr` on `total_min_hcp`/`total_max_hcp` in `seat_viability.py`
- ✅ **C2**: Standardized exception variable `as e` → `as exc` in `profile_cli.py` (2 sites)
- ✅ **D1**: Replaced 5 old-style `%` format strings with f-strings in `lin_encoder.py`
- ✅ **D2**: Replaced string `"WNES"` with tuple `("W", "N", "E", "S")` in `profile_diagnostic.py` (5 sites)

### 49. [x] Fix 9 pyright errors — switch type checker from mypy to pyright
- ✅ `deal_generator.py`: Initialize `chosen_subprofiles`/`chosen_indices` before loop (possibly unbound)
- ✅ `profile_wizard.py`: Removed dead try/except importing 6 nonexistent `_build_*_range_for_prompt` functions
- ✅ `seat_viability.py`: Added `@overload` signatures to `_subprofile_is_viable_light()` for return type narrowing
- ✅ Switched type checker from mypy to pyright in CLAUDE.md

### 50. [x] Comprehensive Help System — menus + y/n prompts
- ✅ **Track A: 4 menus** — Added Help option to Edit Profile Mode, Draft Tools, Extra Constraint, NS Role Mode
- ✅ **Track B: `_yes_no_help()`** — New function in `cli_io.py` accepting "help"/"h"/"?" to print context help and re-prompt
- ✅ **10 help text entries** in `menu_help.py`: 4 menu help texts (edit_profile_mode, draft_tools, extra_constraint, ns_role_mode) + 6 y/n help texts (yn_non_chosen_partner, yn_non_chosen_opponent, yn_edit_weights, yn_edit_roles, yn_exclusions, yn_rotate_deals)
- ✅ **6 `_yes_no` → `_yes_no_help` replacements**: PC inverse, OC inverse, weights, roles, exclusions (wizard_flow.py), rotate deals (orchestrator.py)
- ✅ `_yes_no_help` wired through `wizard_io.py` → `profile_wizard.py` → `wizard_flow.py` (_pw_attr monkeypatch seam)
- ✅ 7 new tests in `test_cli_io.py`; updated monkeypatches in `test_exclusion_menu.py` + `test_wizard_edit_flow.py`

### 51. [x] Code Review #57 — 26 fixes across 16 files
- ✅ **A1**: Removed wasted initial `_pick_once()` call before feasibility retry loop in `deal_generator.py`
- ✅ **A2**: Added draft `*_TEST.json` filtering to `orchestrator._discover_profiles()` (was showing drafts in session picker)
- ✅ **A3**: Added `use_non_chosen_suit` display to PC/OC print functions in `profile_cli.py`
- ✅ **A4**: Replaced raw `input()` with `wiz_io.prompt_str()` in `wizard_flow.py` `_parse_suit_list()`
- ✅ **A5**: Added trailing newline + explicit encoding to `profile_convert.py` file I/O
- ✅ **A6**: Added `qx|oN|` board renumbering in `lin_tools.py` LIN combiner
- ✅ **A7**: Fixed `re.Match` → `re.Match[str]` type annotation in `lin_tools.py`
- ✅ **B1**: Removed dead `create_profile_interactive()` from `wizard_flow.py` (85 lines)
- ✅ **B2**: Removed unused `edit_constraints_interactive` import from `profile_cli.py`
- ✅ **B3**: Removed dead `_input_bool` from `wizard_io.py` and `profile_wizard.py`
- ✅ **B4**: Removed unreachable `if not rows` guard in `failure_report.py`
- ✅ **B5**: Removed unreachable `take <= 0` guard in `deal_generator_v2.py`
- ✅ **B6-B7**: Removed unused `group_lin_files_by_scenario()` + `latest_lin_file_per_scenario()` from `lin_tools.py` + unused imports
- ✅ **C1**: Added type annotation to `_DEBUG_STANDARD_CONSTRUCTIVE_USED` in `deal_generator_types.py`
- ✅ **C2-C3**: Replaced duplicate `Seat`/`Card` aliases with imports from `deal_generator_types` in `seat_viability.py` and `failure_report.py`
- ✅ **C4-C6**: Removed ~26 redundant `getattr` calls across `wizard_flow.py`, `profile_cli.py`, `deal_generator_v2.py`, `profile_store.py`
- ✅ **D1**: Narrowed `except Exception` → `(SetupError, OSError)` in `orchestrator.py` run_setup
- ✅ **D2**: Kept `except Exception` for profile_cli safety nets (correct — top-level wizard catch-all)
- ✅ **D3**: Narrowed `except Exception` → `(JSONDecodeError, TypeError, KeyError, ValueError, OSError)` in `orchestrator._discover_profiles()`
- ✅ **D4**: Removed dead `clear_screen()` fallback in `wizard_io.py`
- ✅ **D5**: Narrowed `except Exception` → `(OSError, ValueError)` in `lin_tools.py` LIN combiner
- ✅ **D6**: Narrowed `except Exception` → `(OSError, ValueError, TypeError, KeyError)` in `deal_output.py` render_deals

### 52. [x] Named Subprofiles
- ✅ Added optional `name: Optional[str] = None` field to SubProfile dataclass (model + serialization)
- ✅ `sub_label()` helper formats "Sub-profile 1 (name)" or "Sub-profile 1" for display
- ✅ Wizard name prompt during creation (optional, Enter to skip)
- ✅ "Edit sub-profile names" menu option (mode 3) for existing profiles
- ✅ Display updates: profile_cli.py (4 sites), wizard_flow.py (6 sites), profile_viability.py (dead sub warnings), menu_help.py
- ✅ PC/OC print: always shows "Target: partner's CHOSEN suit" or "Target: partner's NON-CHOSEN suit (inverse)"
- ✅ Backwards compatible — old profiles load fine with name=None
- ✅ 6 new tests in `test_hand_profile.py` (round-trip, omission, missing defaults, empty→None, sub_label)

### 54. [x] PC/OC Chosen vs Unchosen Prompt
- ✅ Replaced confusing y/n "Target partner's NON-CHOSEN suit (inverse)?" with direct C/U choice
- ✅ PC prompt: "Target partner's CHOSEN or UNCHOSEN RS suit? (C/U)"
- ✅ OC prompt: "Target opponent's CHOSEN or UNCHOSEN RS suit? (C/U)"
- ✅ Updated menu labels: "chosen or inverse" → "chosen or unchosen suit"
- ✅ Updated help text in `menu_help.py`: renamed "Non-Chosen (Inverse)" → "Chosen or Unchosen" throughout
- ✅ Updated display text in `profile_cli.py`: "NON-CHOSEN suit (inverse)" → "UNCHOSEN suit"

### 53. [x] Code Review #58 — 7 fixes across 6 files
- ✅ **B1**: Removed always-true `if chosen_files:` guard in `lin_tools.py` (guaranteed >= 2 by loop above)
- ✅ **B2**: Removed dead dict fallback + redundant `getattr` on `PairOverrideData` in `profile_cli.py`
- ✅ **C1**: Moved docstring before `from __future__` in `lin_encoder.py` (was making `__doc__` = None)
- ✅ **C2**: Replaced redundant `getattr(existing, "rotate_deals_by_default", True)` with direct access in `wizard_flow.py`; updated test dummy
- ✅ **C3**: Replaced 12 redundant `getattr` calls with direct field access on `SubProfile`/`StandardSuitConstraints`/`SuitRange` in `deal_generator_v2.py`
- ✅ **D1**: Converted `_convert_to_lin_deals()` loop-append to list comprehension in `deal_output.py`

### 55. [x] EW Role Mode
- ✅ Added `ew_role_mode` + `ew_driver_seat` to HandProfile (model + serialization)
- ✅ EW coupling in `_select_subprofiles_for_board()` now respects `ew_role_mode` (was always-coupled)
- ✅ EW role usage filtering on SubProfile (`ew_role_usage` field)
- ✅ Wizard prompts for EW role mode editing
- ✅ Validation: `_validate_ew_role_usage_coverage()` in `hand_profile_validate.py`
- ✅ EW coupling viability check in `profile_viability.py`
- ✅ 10 new tests in `test_hand_profile.py`

### 56. [x] Code Review #59 — 3 fixes
- ✅ **C1**: Removed redundant `getattr` for `ew_role_mode` in `profile_viability.py`
- ✅ **C3**: Updated stale EW docstring in `deal_generator.py`
- ✅ **C4**: Updated `wizard_flow.py` docstring to mention EW role usage

### 57. [x] Remove V1 Deal Generator
- ✅ Deleted `deal_generator_v1.py` (783 lines)
- ✅ Removed v1 imports + RS-W-only early-return from `deal_generator.py`
- ✅ Removed `use_rs_w_only_path` from data model, CLI, tests, profile JSONs
- ✅ Removed dead v1-only code: `HardestSeatConfig`, `_DEBUG_STANDARD_CONSTRUCTIVE_USED`, `_get_constructive_mode()`, `MIN_ATTEMPTS_FOR_UNVIABLE_CHECK`, `CONSTRUCTIVE_MAX_SUM_MIN_CARDS`, `MAX_ATTEMPTS_HAND_2_3`
- ✅ Deleted 12 v1-only test files (33 tests removed)
- ✅ Updated remaining tests to use v2 imports

### 60. [x] Update help text for new functionality
- ✅ `main_menu`: Added EW role, sort order; removed "order" (auto-computed)
- ✅ `edit_profile_mode`: Added Mode 3 (sub-profile names), EW role mode, sort order, auto-computed dealing order note
- ✅ `deal_generation_menu`: Added shape-based help, board-level retry, adaptive re-seeding, per-board timing
- ✅ `ns_role_mode`: "N_DRIVER" → "NORTH DRIVES", "S_DRIVER" → "SOUTH DRIVES"
- ✅ `ew_role_mode`: "E_DRIVER" → "EAST DRIVES", "W_DRIVER" → "WEST DRIVES"
- ✅ `yn_edit_roles`: Added note about parallel EW role usage prompt

### 61. [x] Test coverage improvements (+32 tests)
- ✅ 6 tests for `_build_processing_order()` in `test_shape_help_v3.py`
- ✅ 12 tests in new `test_lin_tools_split_renumber.py` (split/renumber LIN boards)
- ✅ 14 tests in new `test_profile_diagnostic_helpers.py` (hand_hcp, suit_count, hand_shape, fmt_row, smoke test)

### 59. [x] Dead code sweep (post-v1 removal)
- ✅ Removed dead `_summarize_profile_viability()` (~44 lines) from `deal_generator_helpers.py`
- ✅ Removed dead `_is_unviable_bucket()` (~11 lines) from `deal_generator_helpers.py`
- ✅ Removed dead `UNVIABLE_MIN_FAILS` / `UNVIABLE_MIN_RATE` constants from `deal_generator_types.py`
- ✅ Updated 4 stale "constructive" comments in test files

### 58. [x] Code Review #60 — 7 fixes across 7 files
- ✅ **B1**: Removed dead `MAX_ATTEMPTS_HAND_2_3` constant from `deal_generator_types.py`
- ✅ **B2**: Consolidated duplicate imports in `wizard_flow.py`
- ✅ **C1**: Removed 4 redundant `getattr` in `hand_profile_validate.py`
- ✅ **C2**: Added `ProfileError` to exception handler in `profile_store.py`
- ✅ **C3**: Updated misleading getattr comments in `deal_generator.py`
- ✅ **C4**: Fixed stale "profile_wizard.py" references in `wizard_flow.py`
- ✅ **D2**: Replaced `object.__setattr__` with `replace()` + dict swap in `seat_viability.py`

### 62. [x] RS cross-seat suit exclusion
- ✅ `_pre_select_rs_suits()` now excludes suits chosen by earlier RS seats from later RS seats
- ✅ Processing order follows dealing_order for deterministic exclusion priority
- ✅ Graceful degradation: if exclusion leaves fewer suits than required, seat is skipped
- ✅ 5 new cross-seat exclusion tests + updated 10 existing RS tests for new `dealing_order` param

### 65. [x] Sort profile listing by version (highest first), then alphabetically
- ✅ Added `_version_sort_key()` helper to `profile_store.py` — parses version strings for descending numeric sort
- ✅ `build_profile_display_map()` sorts unordered profiles by version (highest first), then alphabetically by name
- ✅ Test profiles with `sort_order` (20+) unaffected — they use the `ordered` path

### 67. [x] Move role & exclusion editing into per-subprofile flow
- ✅ Role prompt (NS/EW driver/follower) now happens per-subprofile, right after constraints
- ✅ Exclusion editing (add shapes/rule, remove, help) now happens per-subprofile, right after role
- ✅ New `_assign_role_usage_for_subprofile()` — per-sub role prompt for N/S or E/W seats
- ✅ New `_edit_exclusions_for_subprofile()` — inner exclusion menu without outer sub-picker loop
- ✅ `_build_seat_profile()` now returns `tuple[SeatProfile, List[SubprofileExclusionData]]`
- ✅ Weights remain as post-loop prompt (must sum to 100% across all subs)
- ✅ Single subprofile: auto-assigns "any" role, no prompt
- ✅ `_build_profile()` updated to handle tuple return + backward compat with monkeypatch stubs
- ✅ Legacy `_edit_subprofile_exclusions_for_seat()` kept as wrapper for backward compatibility
- ✅ Skipping a sub-profile now also skips role + exclusion prompts (preserves existing fully)
- ✅ Visual separators: blank line before exclusion gate prompt and before save confirmation
- wizard_flow.py: 1,447 → 1,616 lines (+169)

### 68. [x] Restrict role usage options based on role mode
- ✅ New `_valid_role_options_for_seat()` helper determines valid role usage choices
- ✅ `"no_driver"` mode: auto-assigns `"any"` without prompting (no driver/follower distinction)
- ✅ Fixed driver modes (e.g. `"east_drives"`): driver seat gets `any`/`driver_only`, follower gets `any`/`follower_only`
- ✅ `"random_driver"`: all three options (either seat could drive)
- ✅ Existing defaults clamped to valid options (prevents stale `driver_only` on `no_driver` mode)
- ✅ Updated help text in `menu_help.py`: edit_profile_mode, yn_edit_weights, yn_edit_roles, yn_edit_ew_roles, yn_exclusions, exclusions (wildcard shapes)
- ✅ Fixed Cappeletti profile: typo "Interfernce"→"Interference", E subs `driver_only`→`any`

### 69. [x] Code Review #65 — 1 fix + golden test update
- ✅ **B1 (dead code)**: Removed `_assign_ns_role_usage_interactive()` + `_assign_ew_role_usage_interactive()` from `wizard_flow.py` (123 lines) — superseded by per-subprofile `_assign_role_usage_for_subprofile()`
- ✅ Updated golden test: `Ops interference over our 1NT` → `Our 1 Major & Opponents Interference` (old profile no longer on disk)
- ✅ New profiles: `Opps_Cappeletti_(BBO)_over_our_Strong_1NT_v1.0.json`, `Opps_Open_and_we_Overcall_Cappeletti_v0.9.json`

### 70. [x] RS constraints override standard for chosen suits
- ✅ `_match_standard()` now accepts `rs_skip_suits` — skips per-suit shape/HCP checks for RS-chosen suits (total HCP still checked)
- ✅ `_match_subprofile()` passes `pre_selected_suits` to `_match_standard()` when RS constraint present
- ✅ `_get_suit_maxima()` now **replaces** (not min) standard max_cards with RS max_cards for pre-selected suits
- ✅ Enables tight standard constraints (e.g. max_cards=5) alongside wider RS constraints (e.g. max_cards=6)
- ✅ Aligns matching/dealing with validation concept "RS range overrides the standard one" (`hand_profile_validate.py:131`)
- ✅ Updated Weak 2s profile: W standard max_cards 6→5, max_hcp 10→8, RS min_hcp 5→4

### 71. [x] OC/PC contingent suit pre-allocation
- ✅ `_resolve_contingent_target_suit()` — resolves target suit from opponent/partner RS pre-selections (handles `use_non_chosen_suit`)
- ✅ `_pre_allocate_contingent()` — pre-allocates cards for OC/PC target suit with HCP-targeted rejection sampling (fraction=1.0)
- ✅ `_dispersion_check()` extended with OC/PC tightness block — flags seats with tight contingent constraints
- ✅ `_deal_with_help()` Phase 1c — contingent pre-allocation after RS pre-allocation, accepts `rs_allowed_suits` param
- ✅ Builder wired: `rs_allowed_suits` passed from `_build_single_constrained_deal_v2()` to `_deal_with_help()`
- ✅ OC subprofiles ~2x faster (median 3-4ms → 1.3-1.9ms on Weak 2s profile)
- ✅ 28 tests in `test_contingent_pre_allocation.py` (resolve target suit, pre-allocate, dispersion check, pair viability HCP)

### 72. [x] Code Review #65 — 3 fixes across 2 files
- ✅ **A1**: Fixed `c[-1]` → `c[1]` for suit extraction in `_pre_allocate_contingent()` — consistency with rest of codebase
- ✅ **A2**: Added combined HCP minimum check (`> 40`) to `_pair_jointly_viable()` in `profile_viability.py`
- ✅ **C1**: Fixed stale "NS index-coupled pair" docstring → "NS or EW" in `_pair_jointly_viable()`

### 75. [x] Driver/Follower Role Filtering (Phase A)
- ✅ `_eligible_indices_for_role()` in `deal_generator_helpers.py` — filters subprofile indices by role usage
- ✅ `eligible_indices` param on `_choose_index_for_seat()` — restricts weighted choice to eligible subs
- ✅ `pair` param on `_try_pair_coupling()` — enables role filtering per pair (NS/EW)
- ✅ Call sites updated in `_select_subprofiles_for_board()` to pass pair and role info
- ✅ Driver-only subs never chosen for follower seat, follower-only never for driver
- ✅ `random_driver` mode filters correctly per board
- ✅ `no_driver_no_index` skips filtering entirely

### 76. [x] Bespoke Subprofile Matching (Phase B)
- ✅ `ns_bespoke_map`/`ew_bespoke_map` fields on HandProfile (model + `to_dict`/`from_dict` with string key serialization)
- ✅ `_validate_bespoke_map()` in `hand_profile_validate.py` — validates indices, exhaustiveness, rejects incompatible role modes
- ✅ `bespoke_map` param on `_try_pair_coupling()` — follower picks from map entries instead of forced same-index
- ✅ Removes equal-count requirement when bespoke map is set (driver and follower can have different sub counts)
- ✅ Role filtering + bespoke map combined correctly
- ✅ `_edit_bespoke_map()` in `wizard_flow.py` — multi-select wizard for driver→follower mapping
- ✅ Bespoke map display in `profile_cli.py` — shows driver→follower sub labels
- ✅ 68 tests across `test_role_filtering.py` and `test_bespoke_matching.py`

### 77. [x] Code Review #67 — 4 fixes across 4 files
- ✅ **C1**: Fixed stale "metadata-only" docstring on `ns_role_mode` in `hand_profile_model.py`
- ✅ **C2**: Replaced unnecessary `getattr` with direct access for bespoke map in `profile_cli.py`
- ✅ **C3**: Updated comment in `hand_profile_validate.py` explaining why `getattr` is needed (duck-typed test profiles)
- ✅ **D1**: Removed redundant `both <= 1 sub` guard in `wizard_flow.py` `_edit_bespoke_map()`

### 78. [x] Help menu updates for role filtering + bespoke matching
- ✅ `ns_role_mode` help: Added "Role filtering" and "Bespoke matching" sections
- ✅ `ew_role_mode` help: Same parallel updates
- ✅ `edit_profile_mode` help: Added step 6 for bespoke matching after all seats configured
- ✅ `yn_edit_roles` / `yn_edit_ew_roles` help: Added runtime filtering and bespoke matching notes

### 74. [x] Code Review #66 — 7 fixes across 7 files
- ✅ **C1**: Consistent `Callable[..., None]` type on `_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION` in `deal_generator_types.py`
- ✅ **C2**: Fixed stale "Optional" comment on `SubProfile.standard` in `hand_profile_validate.py` (kept guard for test mocks)
- ✅ **C3**: Removed redundant `if min_cards > 0` ternary guards in `_pre_allocate_contingent()` in `deal_generator_v2.py`
- ✅ **B1/B2/D1**: Removed always-true guards on pair override display in `profile_cli.py` (frozen dataclass guarantees 2 suits + non-None ranges)
- ✅ **B3**: Removed dead `create_profile_from_existing_constraints()` from `profile_wizard.py` (never called)
- ✅ **D3**: Simplified `True if x else False` → `bool(x)` in `wizard_flow.py`
- ✅ **C4**: Fixed misleading "Seats other than N/S/E/W" comment in `wizard_flow.py`
- ✅ **D2**: Removed dead `or []` fallback on `hand_dealing_order` in `hand_profile_validate.py` (validated in `__post_init__`)
- ✅ **D4**: Removed always-false `if seat not in buckets` guards in `hand_profile_model.py`

### 73. [x] Adaptive subprofile re-roll intervals
- ✅ Replaced fixed `SUBPROFILE_REROLL_INTERVAL=150` and `RS_REROLL_INTERVAL=105` with 4 adaptive constants
- ✅ `ADAPTIVE_SUB_REROLL_INITIAL=150` — starting interval (same as old fixed value)
- ✅ `ADAPTIVE_SUB_REROLL_MIN=50` — floor (never re-roll faster than this)
- ✅ `ADAPTIVE_SUB_REROLL_DECAY=0.7` — shrink factor on consecutive failures
- ✅ `ADAPTIVE_RS_REROLL_RATIO=0.7` — RS interval = sub interval × 0.7
- ✅ Builder loop tracks `attempts_since_sub_reroll` / `attempts_since_rs_reroll` counters
- ✅ On sub re-roll: decay interval, reset counters, re-select subprofiles + RS suits
- ✅ Each board starts fresh at the initial interval
- **Benchmark (5 seeds × 500 boards)**: N sub 0 hit rate 17.5% → 19.6% (+2.1pp closer to 25% target), max deviation 9.2pp → 7.6pp, ~6% faster overall

### 66. [x] Sub-profile skip prompt during constraint editing
- ✅ Added Y/n "Edit Sub-profile N?" prompt in `_build_seat_profile()` when editing existing profiles
- ✅ Skipping preserves the existing sub-profile as-is (no re-entry needed)
- ✅ Default is Yes (Enter proceeds to edit as before)
- ✅ Shortened NS/EW role mode "no_driver" label in `profile_cli.py`

### 64. [x] Code Review #64 — 10 fixes across 8 files
- ✅ **A1 (bug)**: Added `ProfileError` to `orchestrator._discover_profiles()` exception handler — was missing, could crash on corrupted-but-valid-JSON profiles
- ✅ **B1 (dead code)**: Removed unused `prompt_choice()` + `TypeVar` import from `cli_prompts.py` — the `prompt_choice` in `profile_cli.py` is a different function
- ✅ **B2 (dead code)**: Removed unreachable seat validation guard in `wizard_flow.py` — `_input_choice` already guarantees valid return
- ✅ **C1 (consistency)**: Removed redundant `.upper()` on `_input_choice` return in `wizard_flow.py`
- ✅ **C2 (consistency)**: Removed redundant `min_cards > 0` guard in `deal_generator_v2.py` — already filtered above
- ✅ **C3 (consistency)**: Removed misleading `weight is not None` check on `float` field in `profile_cli.py`
- ✅ **C4 (consistency)**: Fixed seat iteration order to consistent W-N-S-E in `profile_diagnostic.py`
- ✅ **D1-D2 (simplification)**: Consolidated duplicated RS fallback logic in `deal_generator_v2.py` and `seat_viability.py`
- ✅ **D3 (simplification)**: Unified `_validate_ns_coupling` + `_validate_ew_coupling` → `_validate_pair_coupling` in `profile_viability.py`

### 63. [x] Code Review #63 — 18 fixes across 12 files
- ✅ **A1**: Added `ProfileError` to `profile_cli._load_profiles()` except tuple
- ✅ **A2**: Added draft file filter (`is_draft_path` skip) to `profile_cli._load_profiles()`
- ✅ **B1-B3**: Removed 3 dead wrappers from `wizard_flow.py` (`_validate_profile`, `_prompt_standard_constraints`, `_build_subprofile_for_seat`)
- ✅ **B4-B5**: Removed dead `or` fallbacks and unreachable guard in `hand_profile_validate.py`
- ✅ **B6**: Replaced closure+subn with `sub()` in `lin_tools.py`
- ✅ **C1**: Updated stale module header in `deal_generator_v2.py`
- ✅ **C2**: Changed `ValueError` → `ProfileError` in `profile_viability.py` coupling validators (4 sites)
- ✅ **C3**: Renamed `_ns_pair_jointly_viable` → `_pair_jointly_viable` (generic name)
- ✅ **C4**: Added `HandProfile` type annotation to `profile_diagnostic.py`
- ✅ **C5**: Fixed `profile_convert.py` docstring + added `-> None` return type
- ✅ **D1**: Removed 6 redundant `getattr` on typed fields in `deal_generator_v2.py`
- ✅ **D2**: Removed redundant `getattr` on `weight_percent` in `deal_generator_helpers.py`
- ✅ **D3**: Replaced 3 `getattr` with direct access in `profile_viability.py`
- ✅ **D4**: Replaced mutable list `[0]` with `nonlocal` in `profile_diagnostic.py`
- ✅ **D5**: Moved `import sys` to top-level in `profile_store.py`

---

## Manual Testing (uncommitted changes)

- [ ] Wildcard excluded shapes — enter `64xx` in wizard, verify it excludes all 64xx hands
- [ ] Wildcard validation — confirm `99xx` is rejected, `4333` still requires sum to 13
- [x] PC/OC prompt order — chosen/unchosen question now appears before suit range prompt
- [x] Weight editing menu — 0=Exit, 1=Keep, 2=Even, 3=Manual (replaces old y/n prompt)
- [x] Seat editing save & exit — press "e" to save and skip remaining seats
- [x] Edit subprofile names before constraints — say Yes at prompt, rename subs, then verify names carry through
- [ ] Profile JSON updates — Our 1 Major load correctly

---

## Consider

- [ ] Pair constraint around points and suit count

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
