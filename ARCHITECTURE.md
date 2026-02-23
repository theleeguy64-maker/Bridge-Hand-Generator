# Bridge Hand Generator - Architecture

## Module Structure

```
bridge_engine/
├── deal_generator.py        (358 lines) - Facade: subprofile selection + generate_deals() + re-exports
├── deal_generator_v2.py   (1,222 lines) - v2 shape-help helpers + v2 builder (active path)
├── deal_generator_types.py  (227 lines) - Types, constants, dataclasses, exception, debug hooks (leaf module)
├── deal_generator_helpers.py (384 lines) - Shared utilities: viability, HCP, deck, subprofile weights, vulnerability/rotation
├── hand_profile_model.py    (911 lines) - Data models (incl. EW role mode)
├── seat_viability.py        (603 lines) - Constraint matching + RS pre-selection threading
├── hand_profile_validate.py (610 lines) - Validation (incl. EW role usage coverage)
├── profile_diagnostic.py     (213 lines) - Generic profile diagnostic runner (Admin menu)
├── orchestrator.py          (473 lines) - CLI/session management + generic menu loop
├── profile_cli.py         (1,038 lines) - Profile commands (incl. EW role mode editing)
├── profile_wizard.py        (157 lines) - Profile creation UI
├── profile_convert.py        (40 lines) - Profile format conversion
├── wizard_flow.py         (1,616 lines) - Wizard steps, per-sub role/exclusion editing, RS/PC/OC prompts
├── wizard_io.py             (104 lines) - Wizard I/O helpers
├── profile_viability.py     (389 lines) - Profile-level viability + cross-seat feasibility + EW coupling
├── profile_store.py         (310 lines) - JSON persistence (atomic writes, error-tolerant loading, display ordering)
├── menu_help.py             (601 lines) - Menu help text (incl. EW role mode)
├── lin_tools.py             (413 lines) - LIN file operations
├── deal_output.py           (326 lines) - Deal rendering
├── lin_encoder.py           (188 lines) - LIN format encoding
├── setup_env.py             (216 lines) - RNG seed management
├── cli_io.py                (163 lines) - CLI utilities
├── cli_prompts.py            (49 lines) - CLI prompts
├── hand_profile.py           (36 lines) - Exports
└── __main__.py               (14 lines) - Entry point
```

## Data Model Hierarchy

```
HandProfile (frozen dataclass)
├── seat_profiles: Dict[Seat, SeatProfile]
│   └── SeatProfile
│       └── subprofiles: List[SubProfile]
│           └── SubProfile
│               ├── standard: StandardSuitConstraints
│               │   ├── spades/hearts/diamonds/clubs: SuitRange
│               │   │   ├── min_cards, max_cards
│               │   │   └── min_hcp, max_hcp
│               │   └── total_hcp_min, total_hcp_max
│               ├── random_suit_constraint: Optional[RandomSuitConstraintData]
│               │   ├── allowed_suits, required_suits_count
│               │   ├── per_suit_range: SuitRange
│               │   └── pair_overrides: Dict
│               ├── partner_contingent_constraint: Optional[PartnerContingentData]
│               │   └── use_non_chosen_suit: bool  (target inverse of partner's RS choice)
│               ├── opponents_contingent_suit_constraint: Optional[OpponentContingentSuitData]
│               │   └── use_non_chosen_suit: bool  (target inverse of opponent's RS choice)
│               ├── weight_percent: float
│               └── ns_role_usage: str ("any", "driver_only", "follower_only")
├── hand_dealing_order: List[Seat]
├── dealer: Seat
├── ns_role_mode: str ("no_driver_no_index", "north_drives", etc.)
├── ns_driver_seat: Optional[Callable]
├── ew_role_mode: str ("no_driver_no_index", "east_drives", etc.)
├── ew_driver_seat: Optional[Callable]
├── is_invariants_safety_profile: bool
└── sort_order: Optional[int]  (custom display numbering)
```

## Pipeline Flow

### Entry Point
```python
generate_deals(setup, profile, num_deals, enable_rotation=True) -> DealSet
```

### Stage 0-2: Viability Checking
```
validate_profile()           # Structural validity
    ↓
validate_profile_viability() # Constraint feasibility (3 steps):
    Step 1: validate_profile_viability_light()  # Per-seat bounds checks
    Step 2: _validate_ns_coupling()             # NS index-coupling joint viability
    Step 3: _check_cross_seat_subprofile_viability()  # Cross-seat HCP + card-count (#16)
            → warns for dead subprofiles
            → raises ProfileError if ALL subs on any seat are dead
    ↓
_subprofile_is_viable_light() # Quick bounds check
    ↓
_subprofile_is_viable()       # Deal & match test
```

### Stage C: Constrained Deal Generation

**v2** (current active path — shape-based help):
```python
_build_single_constrained_deal_v2(rng, profile, board_number, debug_board_stats)
```

## Failure Attribution System

### Per-Attempt Tracking
```python
checked_seats_in_attempt: List[Seat]  # Seats we processed
first_failed_seat: Optional[Seat]     # Who failed
first_failed_stage_idx: int           # Index in checked list
```

### Per-Board Counters
```python
seat_fail_as_seat[seat]           # Seat was first to fail
seat_fail_global_other[seat]      # Seat passed, later seat failed
seat_fail_global_unchecked[seat]  # Seat never checked (early break)
seat_fail_hcp[seat]               # Failure was HCP-driven
seat_fail_shape[seat]             # Failure was shape-driven
```

### Attribution Logic
```
On attempt failure:
  first_failed_seat = seat that failed

  For seats checked BEFORE failure:
    seat_fail_global_other[seat] += 1

  For seats NOT checked:
    seat_fail_global_unchecked[seat] += 1

  seat_fail_as_seat[first_failed_seat] += 1
```

## Shape-Based Help System (v2)

**Key insight:** Select subprofiles FIRST, then use shape probability table to
identify tight seats and pre-allocate their suit minima (75% for standard, 100% for RS with HCP targeting).

**Pipeline:**
```
_select_subprofiles_for_board(rng, profile, dealing_order)
    → retry up to MAX_SUBPROFILE_FEASIBILITY_RETRIES if _cross_seat_feasible() fails (#16)
    ↓
_pre_select_rs_suits(rng, chosen_subprofiles) → Dict[Seat, List[str]]
    ↓
_dispersion_check(chosen_subs, rs_pre_selections)  → set of tight seats
    ↓
_deal_with_help(rng, deck, subs, tight_seats, order, rs_pre_selections)
    Phase 1: Pre-allocate ALL tight seats (standard + RS)
    Phase 2: HCP feasibility check on all pre-allocated seats
    Phase 3: Fill each seat to 13 cards (last seat gets pre-allocated + remainder)
    ↓
_match_seat(... rs_pre_selections) per seat (RS first, then others)
    ↓
Success → Deal | Failure → retry (up to MAX_BOARD_ATTEMPTS)
    ↓ (every SUBPROFILE_REROLL_INTERVAL attempts)
Re-select subprofiles (different N/E combos) + RS suits
    ↓ (every RS_REROLL_INTERVAL attempts)
Re-select RS suits to avoid "stuck with bad suit" scenarios
    ↓ (on board exhaustion)
Board-level retry in generate_deals (up to MAX_BOARD_RETRIES)
    ↓ (if board elapsed > RESEED_TIME_THRESHOLD_SECONDS)
Adaptive re-seed: replace RNG with fresh SystemRandom seed
```

**Constants:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `SHAPE_PROB_GTE` | Dict[0-13→float] | P(>=N cards in suit) |
| `SHAPE_PROB_THRESHOLD` | 0.19 | Cutoff for "tight" seats |
| `PRE_ALLOCATE_FRACTION` | 0.75 | Fraction of standard suit minima to pre-allocate |
| `RS_PRE_ALLOCATE_FRACTION` | 1.0 | Fraction of RS suit minima to pre-allocate (full, with HCP targeting) |
| `RS_REROLL_INTERVAL` | 500 | Re-select RS suits every N attempts |
| `SUBPROFILE_REROLL_INTERVAL` | 1000 | Re-select subprofiles every N attempts |
| `RS_PRE_ALLOCATE_HCP_RETRIES` | 10 | Rejection sampling retries for HCP-targeted RS pre-alloc |
| `MAX_BOARD_RETRIES` | 50 | Retries per board in generate_deals() |
| `RESEED_TIME_THRESHOLD_SECONDS` | 1.75 | Per-board wall-clock budget before adaptive re-seeding |
| `MAX_SUBPROFILE_FEASIBILITY_RETRIES` | 100 | Max retries for cross-seat feasible subprofile combo (#16) |
| `FULL_DECK_HCP_SUM` | 40 | Total HCP across all 52 cards |
| `FULL_DECK_HCP_SUM_SQ` | 120 | Sum of squared HCP values across all 52 cards |
| `MAX_HAND_HCP` | 37 | Maximum HCP in a 13-card hand; "no real cap" sentinel |

**Functions** (in `deal_generator_v2.py` + `deal_generator_helpers.py`):
- `_pre_select_rs_suits(rng, chosen_subs)` → Dict[Seat, List[str]] — pre-select RS suits before dealing
- `_dispersion_check(chosen_subs, threshold, rs_pre_selections)` → set of tight seats
- `_random_deal(rng, deck, n)` → List[Card] (mutates deck)
- `_pre_allocate(rng, deck, subprofile, fraction)` → List[Card] (mutates deck)
- `_pre_allocate_rs(rng, deck, subprofile, pre_selected_suits, fraction)` → List[Card] (mutates deck)
- `_deal_with_help(rng, deck, subs, tight_seats, order, rs_pre_selections)` → (Dict[Seat, List[Card]], None) | (None, Seat)
- `_select_subprofiles_for_board(rng, profile, dealing_order)` → (subs, indices)
- `_build_single_constrained_deal_v2(rng, profile, board_number)` → Deal

**RS Pre-Selection** (`#8`):

Before dealing, `_pre_select_rs_suits()` randomly chooses which RS suits to use
for each seat with an RS constraint. This makes RS constraints visible to the
dispersion check and pre-allocation, which previously only saw standard constraints.

```
For each RS seat:
    chosen_suits = rng.sample(allowed_suits, required_suits_count)
    → used by _dispersion_check to flag tight RS seats
    → used by _pre_allocate_rs to pre-deal cards of chosen suit
    → used by _match_seat to skip random suit selection (use pre-committed suits)
```

The 3-phase `_deal_with_help` restructure ensures ALL tight seats (including the
last seat in dealing order) get pre-allocation, not just the first N-1.

**HCP Feasibility Check** (`ENABLE_HCP_FEASIBILITY_CHECK = True`):

After pre-allocation, checks whether the remaining random fill can plausibly
land the seat's total HCP within its target range.  Uses finite population
sampling statistics (expected value ± 1 SD).

```
drawn_HCP + E[additional] ± SD → [ExpDown, ExpUp]
Reject if ExpDown > target_max OR ExpUp < target_min
```

Functions:
- `_card_hcp(card)` → A=4, K=3, Q=2, J=1, else 0
- `_deck_hcp_stats(deck)` → (hcp_sum, hcp_sum_sq)
- `_check_hcp_feasibility(drawn_hcp, cards_remaining, deck_size, ...)` → bool
- `_deal_with_help(...)` → `(hands, None)` or `(None, rejected_seat)`

Constants: `ENABLE_HCP_FEASIBILITY_CHECK = True`, `HCP_FEASIBILITY_NUM_SD = 1.0`

**Performance Optimizations (#10, #15):**
- `_MASTER_DECK` module-level constant — avoids 52 string concatenations per attempt
- `_CARD_HCP` pre-built dict — O(1) HCP lookup per card, eliminates 4.5M+ function calls per run (#15)
- `_random_deal()` uses `deck[:take]` + `del` — deck is already shuffled, no need for `rng.sample()`
- `_pre_allocate()` / `_pre_allocate_rs()` build suit index once with pre-initialized dict, remove all in one pass
- Incremental HCP tracking in `_deal_with_help()` Phase 2 — uses known full-deck values (40, 120)
- Early total-HCP pre-check in v2 builder — quick O(13) sum before full `_match_seat()`
- `_match_standard()` unrolled suit loop — direct attribute access, no temporary list construction

**Constrained Fill (#11):**

Phase 3 of `_deal_with_help()` uses `_constrained_fill()` instead of `_random_deal()` for
non-last seats.  Walks the shuffled deck and skips cards that would:
1. Bust a suit's max_cards (shape constraint enforcement)
2. Push total HCP over total_max_hcp (HCP constraint enforcement — spot cards always accepted)
3. Exceed per-suit HCP cap for RS suits (#13 — `rs_suit_hcp_max` param, spot cards always accepted)

Skipped cards remain in the deck for other seats.  `_get_suit_maxima()` extracts effective
per-suit maximums from standard + RS constraints (including pair_overrides).

`PRE_ALLOCATE_FRACTION` increased 0.50 → 0.75 for more aggressive standard pre-allocation.
`RS_PRE_ALLOCATE_FRACTION` = 1.0 — RS suits are fully populated at pre-allocation time
with HCP targeting, avoiding blind random fill that busted RS suit HCP windows.

**Status:** Profiles A-E all work. Profile E (6 spades + 10-12 HCP) generates
successfully with v2 shape help + HCP feasibility rejection. "Defense to 3 Weak 2s"
generates 6 boards in ~1.5s (was ~50s before full RS pre-allocation, was 0/20 before RS pre-selection).

**Tests:** 75 in `test_shape_help_v3.py`, 36 in `test_hcp_feasibility.py`, 7 in `test_profile_e_v2_hcp_gate.py`, 32 in `test_rs_pre_selection.py`, 2 in `test_defense_weak2s_diagnostic.py`

## Index Coupling

### NS Coupling
```
If ns_role_mode != "no_driver_no_index" AND both N/S have >1 subprofile:
  driver = ns_driver_seat() or first NS seat in dealing_order
  follower = the other NS seat

  driver_index = weighted_choice(driver's subprofiles)
  follower_index = driver_index  # Forced to match
```

### EW Coupling
```
If ew_role_mode != "no_driver_no_index" AND both E/W have >1 subprofile:
  driver = ew_driver_seat() or first EW seat in dealing_order
  follower = the other EW seat

  driver_index = weighted_choice(driver's subprofiles)
  follower_index = driver_index  # Forced to match
```

## Processing Order

**Critical ordering rules:**

1. **RS seats processed first** - So PC/OC seats can see partner/opponent's RS choice
2. **Dealing order matters** - Affects which seat is "driver" for coupling
3. **First failure stops attempt** - Affects attribution for unchecked seats

```python
processing_order = rs_seats_sorted + non_rs_constrained_seats
```

## Dealing Order Design

**Auto-computed at runtime (#37):**

`_compute_dealing_order(chosen_subprofiles, dealer)` in `deal_generator_v2.py` computes
dealing order after subprofile selection, placing the **least constrained seat last**
(gets v2 remainder advantage — all remaining cards without constrained fill).

**Risk scoring** (per chosen subprofile):
- RS = 1.0, PC/OC = 0.5, standard = 0.0
- Tiebreakers: narrower HCP range first, then clockwise from dealer
- Sorted descending: highest risk first, lowest risk (least constrained) **last**

Recomputed on each subprofile re-roll (different subs → different last seat).

The stored `hand_dealing_order` field is retained for NS/EW coupling driver selection
but is no longer editable by users. Wizard/CLI no longer prompt for dealing order.

Tests: 9 tests for `_compute_dealing_order()` in `test_shape_help_v3.py`

## Profile Inventory

| sort_order | Profile Name | File |
|-----------|-------------|------|
| 20 | Profile A Test - Loose constraints | `Profile_A_Test_-_Loose_constraints_v0.1.json` |
| 21 | Profile B Test - tight Suit constraints | `Profile_B_Test_-_tight_suit_constraints_v0.1.json` |
| 22 | Profile C Test - tight points constraints | `Profile_C_Test_-_tight_points_constraints_v0.1.json` |
| 23 | Profile D Test - tight point and suit constraints | `Profile_D_Test_-_tight_and_suit_point_constraint_v0.1.json` |
| 24 | Profile E Test - tight point and suit constraints_plus | `Profile_E_Test_-_tight_and_suit_point_constraint_plus_v0.1.json` |
| — | Big Hands | `Big_Hands_v0.1.json` |
| — | Defense to 3 Weak 2s - Multi Overcall Shapes | `Defense_to_3_Weak_2s_-_Multi_Overcall_Shapes_v0.9.json` |
| — | Opps_Open_&_Our_TO_Dbl | `Opps_Open_&_Our_TO_Dbl_v0.9.json` |
| — | Opps_Open_&_Our_TO_Dbl_Balancing | `Opps_Open_&_Our_TO_Dbl_Balancing_v0.9.json` |
| — | Ops interference over our 1NT | `Ops_interference_over_our_1NT_v0.9.json` |
| — | Our 1 Major & Opponents Interference | `Our_1_Major_&_Opponents_Interference_v0.2.json` |
| — | Responding with a Major to 1NT Opening | `Responding_with_a_Major_to_1NT_Opening_v0.9.json` |

Profiles with `sort_order` appear at their fixed positions; profiles without `sort_order` are sorted by version (highest first), then alphabetically by name.

## Benchmark Portfolio

5 profiles spanning trivial → hardest. Script: `benchmark_portfolio.py [num_boards]`.

| # | Profile | Sub Combos | Key Constraint |
|---|---------|-----------|----------------|
| 1 | Profile A (Loose) | 1×1×1×1 = 1 | No constraints (baseline overhead) |
| 2 | Profile D (Suit+Pts) | 1×1×1×1 = 1 | N: 5-6 spades + 10-12 HCP |
| 3 | Profile E (Suit+Pts+) | 1×1×1×1 = 1 | N: exactly 6 spades + 10-12 HCP |
| 4 | Our 1 Major & Interference | 1×3×1×1 = 3 | All 4 seats: RS+PC+OC |
| 5 | Defense to 3 Weak 2s | 1×4×1×4 = 16 | OC+RS mixing, 16 sub combos |

**Baseline (20 boards, seed=778899) — with v0.3 Weak 2s profile:**

| Profile | Wall(s) | Avg(ms) | Med(ms) | P95(ms) | Max(ms) |
|---------|---------|---------|---------|---------|---------|
| Profile A | 0.001 | 0.0 | 0.0 | 0.1 | 0.1 |
| Profile D | 0.002 | 0.1 | 0.1 | 0.3 | 0.3 |
| Profile E | 0.002 | 0.1 | 0.1 | 0.2 | 0.2 |
| Our 1 Major | 0.044 | 2.2 | 0.5 | 9.3 | 9.3 |
| Defense Weak 2s | 0.298 | 14.9 | 2.8 | 77.1 | 77.1 |
| **TOTAL** | **0.348** | | | | |

## Debug Hooks

```python
_DEBUG_ON_MAX_ATTEMPTS(...)              # Called on exhaustion
_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION(...) # Called on each failed attempt
```

## Key Functions

### deal_generator_types.py (leaf — no bridge_engine imports)
```python
# Types: Seat, Card, SeatFailCounts, SeatSeenCounts
# Dataclasses: Deal, DealSet, SuitAnalysis
# Exception: DealGenerationError
# Constants: MAX_BOARD_ATTEMPTS, SHAPE_PROB_GTE, PRE_ALLOCATE_FRACTION, RS_PRE_ALLOCATE_FRACTION, etc.
# Debug hooks: _DEBUG_ON_MAX_ATTEMPTS, _DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION
# Master deck: _MASTER_DECK
# Pre-built HCP: _CARD_HCP (dict of all 52 cards → HCP values)
```

### deal_generator_helpers.py
```python
# Viability
classify_viability(successes, attempts) -> str
_compute_viability_summary(fail_counts, seen_counts) -> Dict

# Subprofile weights
_weighted_choice_index(rng, weights) -> int
_weights_for_seat_profile(seat_profile) -> List[float]
_choose_index_for_seat(rng, seat_profile) -> int

# Deck
_build_deck() -> List[Card]

# HCP utilities
_card_hcp(card) -> int
_deck_hcp_stats(deck) -> (hcp_sum, hcp_sum_sq)
_check_hcp_feasibility(drawn_hcp, cards_remaining, deck_size, ...) -> bool

# Simple generator + enrichment
_deal_single_board_simple(rng, board_number, dealer, dealing_order) -> Deal
_apply_vulnerability_and_rotation(rng, deals, rotate) -> List[Deal]
```

### deal_generator.py (facade — 358 lines)
```python
# Public API
generate_deals(setup, profile, num_deals, enable_rotation) -> DealSet

# Coupling + subprofile selection (kept here for monkeypatch compatibility)
_try_pair_coupling(rng, seat_profiles, seat_a, seat_b, driver_seat, chosen_subs, chosen_indices)
_select_subprofiles_for_board(rng, profile, dealing_order) -> (subs, indices)

# Re-exports from deal_generator_v2
_build_single_constrained_deal_v2, _dispersion_check, _pre_select_rs_suits,
_random_deal, _get_suit_maxima, _constrained_fill, _pre_allocate,
_pre_allocate_rs, _deal_with_help,
_compute_dealing_order, _subprofile_constraint_type
```

### deal_generator_v2.py (v2 shape-help — 1,222 lines)
```python
# v2 shape help helpers
_dispersion_check(chosen_subs, threshold, rs_pre_selections) -> set[Seat]
_pre_select_rs_suits(rng, chosen_subs) -> Dict[Seat, List[str]]
_random_deal(rng, deck, n) -> List[Card]
_get_suit_maxima(subprofile, rs_pre_selected) -> Dict[str, int]
_constrained_fill(deck, n, pre_cards, suit_maxima, total_max_hcp, rs_suit_hcp_max=None) -> List[Card]
_pre_allocate(rng, deck, subprofile, fraction) -> List[Card]
_pre_allocate_rs(rng, deck, subprofile, pre_selected_suits, fraction) -> List[Card]
_deal_with_help(rng, deck, subs, tight_seats, order, rs_pre_selections) -> (hands, None) | (None, Seat)

# Dealing order auto-compute (#37)
_subprofile_constraint_type(sub) -> str  # "rs", "pc", "oc", or "standard"
_compute_dealing_order(chosen_subprofiles, dealer) -> List[Seat]  # least constrained last
_build_processing_order(chosen_subs, dealing_order) -> List[Seat]  # RS seats first

# v2 builder (active production path)
_build_single_constrained_deal_v2(rng, profile, board_number) -> Deal

# Late import pattern: reads _dg.MAX_BOARD_ATTEMPTS, _dg.ENABLE_HCP_FEASIBILITY_CHECK,
# _dg._DEBUG_ON_* through facade module at call time for monkeypatch compatibility.
```

### seat_viability.py
```python
_match_seat(profile, seat, hand, seat_profile, chosen_sub, ..., rs_pre_selections) -> (bool, Optional[List[str]])
_match_subprofile(analysis, seat, sub, random_suit_choices, rng, pre_selected_suits) -> (bool, Optional[List[str]])
_match_standard(analysis, std) -> bool
_match_random_suit_with_attempt(..., pre_selected_suits) -> (bool, Optional[List[str]])
_match_partner_contingent(...) -> bool
_compute_suit_analysis(hand) -> SuitAnalysis
```

### hand_profile_model.py
```python
SubProfile.to_dict() -> Dict
SubProfile.from_dict(data) -> SubProfile
SeatProfile(seat, subprofiles)
HandProfile(seat_profiles, dealer, dealing_order, ...)
```

## Type Checking

**pyright** — 0 errors across 27 source files.

```bash
npx pyright bridge_engine/
```

## Test Coverage

**512 passed** organized by:
- Core matching: `test_seat_viability*.py`
- Index coupling: `test_f3_opener_responder_coupling.py`
- Profile viability: `test_profile_viability_*.py`
- Benchmarks: `test_profile_e_*.py`
- **Shape help**: `test_shape_help_v3.py` (94 tests — dispersion, pre-alloc, RS suit HCP, auto-compute dealing order, build processing order)
- **HCP feasibility**: `test_hcp_feasibility.py` (36 tests — unit + integration)
- **Profile E e2e**: `test_profile_e_v2_hcp_gate.py` (7 tests — v2 builder + pipeline)
- **RS pre-selection**: `test_rs_pre_selection.py` (32 tests — B1-B4 unit tests)
- **Defense to Weak 2s**: `test_defense_weak2s_diagnostic.py` (2 tests — diagnostic + pipeline)
- **Cross-seat feasibility**: `test_cross_seat_feasibility.py` (39 tests — accessors, core, dead sub detection, runtime retry, integration)
- **v2 comparison**: `test_v2_comparison.py` (6 gated — `RUN_V2_BENCHMARKS=1`)
- **OC non-chosen suit**: `test_oc_non_chosen_suit.py` (25 tests — data model, helper, matching, regression, graceful fail, validation, integration, edge cases)
- **PC non-chosen suit**: `test_pc_non_chosen_suit.py` (18 tests — data model, matching, regression, graceful fail, validation, integration)
- **LIN split/renumber**: `test_lin_tools_split_renumber.py` (12 tests — split into boards, renumber, edge cases)
- **Diagnostic helpers**: `test_profile_diagnostic_helpers.py` (14 tests — hand_hcp, suit_count, hand_shape, fmt_row, smoke test)

- **Profile mgmt actions**: `test_profile_mgmt_actions.py` (9 tests — edit/delete/save-as/draft-tools)
- **Menu dispatch**: `test_profile_mgmt_menus.py` (4 tests — profile manager + admin menu loops)
- **Wizard editing**: `test_wizard_edit_flow.py` (5 tests — skip/edit seats, autosave, constraints roundtrip, exclusions)

**Untested modules** (low risk):
- `profile_convert.py` - file I/O logic (should add tests)
- `cli_prompts.py`, `menu_help.py` - minimal/static

---

## Known Structural Issues

### Duplicate Definitions (need cleanup)

| File | Issue |
|------|-------|
| `orchestrator.py` | `_format_nonstandard_rs_buckets()` x2 — *removed in #4b* |

*Resolved*: `_weights_for_seat_profile()`, `_choose_index_for_seat()`, `_select_subprofiles_for_board()` — duplicates cleaned up.

### Orphaned/Dead Code

| File | Issue |
|------|-------|
| `orchestrator.py` | Unreachable try-except |
*Resolved*: `_build_rs_bucket_snapshot()`, `_nonstandard_constructive_help_enabled()`, v2 nonstandard stubs, `ENABLE_CONSTRUCTIVE_HELP` flags, debug hooks — removed.

*Resolved*: Cascading dead code: `_shadow_probe_nonstandard_constructive()`, `_nonstandard_constructive_v2_policy()`, `_build_constraint_flags_per_seat()`, inline PC/OC nudge blocks, RS bucket tracking, shadow functions in orchestrator.py — removed.

*Resolved*: `passrandom_suit_choices` merge artifact — cleaned up.

### Missing Implementations

*Resolved*: `profile_store.py` `list_drafts()` — already implemented (lines 59-65).

*Resolved*: `hand_profile_model.py` duplicate `SubprofileExclusionClause` — consolidated to single frozen definition with serialization. Added missing `to_dict()`/`from_dict()` to `SubprofileExclusionData`. Fixed `validate()` bug (`len(seat_profile.subprofiles)` not `len(seat_profiles)`).

*Resolved*: `profile_cli.py` dead `_render_full_profile_details_text()` — removed.

*Resolved*: `profile_store.py` safety — `_load_profiles()` error-tolerant with try/except; all writes use `_atomic_write()` (tempfile + os.replace); consistent trailing newline; `delete_draft_for_canonical()` narrowed to `except OSError`.

*Resolved*: `wizard_flow.py` `_prompt_suit_range()` — `prompt_int()` called with swapped arguments (default/minimum/maximum in wrong order), causing OC/PC suit range prompts to show inverted bounds like `>=13 and <=1`.

*Resolved*: `profile_cli.py` metadata edit — version change now saves to a new versioned file (keeps old version intact). Draft cleanup (`delete_draft_for_canonical`) added to constraints-only edit and save-as-new-version paths.
