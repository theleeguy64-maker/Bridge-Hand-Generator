# Bridge Hand Generator - Architecture

## Module Structure

```
bridge_engine/
├── deal_generator.py      (2,530 lines) - Main pipeline + v2 shape help + HCP feasibility + RS pre-selection + board retry + perf opts
├── hand_profile_model.py    (921 lines) - Data models
├── seat_viability.py        (615 lines) - Constraint matching + RS pre-selection threading
├── hand_profile_validate.py (512 lines) - Validation
├── orchestrator.py          (528 lines) - CLI/session management + timing
├── profile_cli.py           (968 lines) - Profile commands
├── profile_wizard.py        (164 lines) - Profile creation UI
├── profile_viability.py     (108 lines) - Profile-level viability
├── profile_store.py         (208 lines) - JSON persistence
├── lin_tools.py             (459 lines) - LIN file operations
├── deal_output.py           (330 lines) - Deal rendering
├── lin_encoder.py           (188 lines) - LIN format encoding
├── setup_env.py             (214 lines) - RNG seed management
├── cli_io.py                (197 lines) - CLI utilities
├── cli_prompts.py           (101 lines) - CLI prompts
├── text_output.py            (67 lines) - Text formatting
└── hand_profile.py           (34 lines) - Exports
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
│               ├── opponents_contingent_suit_constraint: Optional[OpponentContingentSuitData]
│               ├── weight_percent: float
│               └── ns_role_usage: str ("any", "driver_only", "follower_only")
├── hand_dealing_order: List[Seat]
├── dealer: Seat
├── ns_index_coupling_enabled: bool
├── ns_driver_seat: Optional[Callable]
└── is_invariants_safety_profile: bool
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
validate_profile_viability() # Constraint feasibility
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

**v1** (legacy, still available for rollback):
```python
_build_single_constrained_deal(rng, profile, board_number, debug_board_stats)
```

**v1 per-board flow:**
```
1. Select subprofiles
   _select_subprofiles_for_board(rng, profile, dealing_order)
       → chosen_subs: Dict[Seat, SubProfile]
       → chosen_indices: Dict[Seat, int]

2. Determine helper seat (if constructive enabled)
   _choose_hardest_seat_for_board(...)
       → helper_seat: Optional[Seat]

3. Attempt loop (up to MAX_BOARD_ATTEMPTS = 10,000)
   ┌──────────────────────────────────────────────┐
   │ Build deck → shuffle                          │
   │ Deal 13 cards per seat                        │
   │ (or constructive build for helper seat)       │
   │                                               │
   │ For each seat in processing_order:            │
   │   _match_seat(profile, seat, hand, ...)       │
   │       ├─ _match_standard(analysis, std)       │
   │       └─ _match_random_suit_with_attempt(...) │
   │          or _match_partner_contingent(...)    │
   │          or _match_opponent_contingent(...)   │
   │                                               │
   │   If failed:                                  │
   │     Record failure attribution                │
   │     Break → retry                             │
   │                                               │
   │ If all matched → return Deal                  │
   └──────────────────────────────────────────────┘

4. On exhaustion → raise DealGenerationError
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

## Constructive Help System

### v1: Standard Constructive

**5 Gates (ALL must pass):**
1. `helper_seat is not None`
2. `not _seat_has_nonstandard_constraints(profile, helper_seat)`
3. `_is_shape_dominant_failure(seat, hcp, shape, ratio)` - skip if HCP-dominant
4. `constructive_minima = _extract_standard_suit_minima(...)`  (non-empty)
5. `sum(constructive_minima.values()) <= CONSTRUCTIVE_MAX_SUM_MIN_CARDS`

**Build path:**
```python
_construct_hand_for_seat(rng, deck, min_suit_counts)
  → For each suit with minimum:
      Draw required cards from that suit
  → Fill remaining to 13 from rest of deck
```

### v2: Nonstandard Constructive (Removed)

*Fully removed in dead code cleanup (#4, #4b). Policy seam, RS bucket tracking,
PC/OC nudge blocks, and shadow probes have all been deleted.*

### v3: Shape-Based Help System (✅ D0-D6 Complete, RS Pre-Selection #8 Complete)

**Key insight:** Select subprofiles FIRST, then use shape probability table to
identify tight seats and pre-allocate 50% of their suit minima.

**Pipeline:**
```
_select_subprofiles_for_board(rng, profile, dealing_order)
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
```

**Constants:**
| Constant | Value | Purpose |
|----------|-------|---------|
| `SHAPE_PROB_GTE` | Dict[0-13→float] | P(>=N cards in suit) |
| `SHAPE_PROB_THRESHOLD` | 0.19 | Cutoff for "tight" seats |
| `PRE_ALLOCATE_FRACTION` | 0.50 | Fraction of suit minima to pre-allocate |
| `RS_REROLL_INTERVAL` | 500 | Re-select RS suits every N attempts |
| `SUBPROFILE_REROLL_INTERVAL` | 1000 | Re-select subprofiles every N attempts |
| `RS_PRE_ALLOCATE_HCP_RETRIES` | 10 | Rejection sampling retries for HCP-targeted RS pre-alloc |
| `MAX_BOARD_RETRIES` | 50 | Retries per board in generate_deals() |

**Functions** (all in `deal_generator.py`):
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

**Performance Optimizations (#10):**
- `_MASTER_DECK` module-level constant — avoids 52 string concatenations per attempt
- `_random_deal()` uses `deck[:take]` + `del` — deck is already shuffled, no need for `rng.sample()`
- `_pre_allocate()` / `_pre_allocate_rs()` build suit index once, remove all in one pass
- Incremental HCP tracking in `_deal_with_help()` Phase 2 — uses known full-deck values (40, 120)
- Early total-HCP pre-check in v2 builder — quick O(13) sum before full `_match_seat()`
- `_match_standard()` unrolled suit loop — direct attribute access, no temporary list construction

**Status:** Profiles A-E all work. Profile E (6 spades + 10-12 HCP) generates
successfully with v2 shape help + HCP feasibility rejection. "Defense to 3 Weak 2s"
generates 6 boards in ~50s via board-level retry (was 0/20 before RS pre-selection).

**Tests:** 75 in `test_shape_help_v3.py`, 36 in `test_hcp_feasibility.py`, 7 in `test_profile_e_v2_hcp_gate.py`, 32 in `test_rs_pre_selection.py`, 2 in `test_defense_weak2s_diagnostic.py`

## Index Coupling

### NS Coupling
```
If ns_index_coupling_enabled AND both N/S have >1 subprofile:
  driver = ns_driver_seat() or first NS seat in dealing_order
  follower = the other NS seat

  driver_index = weighted_choice(driver's subprofiles)
  follower_index = driver_index  # Forced to match
```

### EW Coupling
```
Always coupled when both E/W have >1 subprofile with equal lengths:
  driver = first EW seat in dealing_order
  Both use same index
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

**Default generation** (Steps 1,3,4,5 complete):
- `_default_dealing_order(dealer)` returns dealer + clockwise
- `HandProfile.from_dict()` auto-generates if missing
- User can override in JSON or wizard

**Base Smart Hand Order** (✅ Complete):
| Priority | Condition | Action |
|----------|-----------|--------|
| 1 | Seat has RS | RS seat first (sorted by risk, clockwise tiebreaker) |
| 2 | NS driver set | NS driver next; else next NS clockwise |
| 3 | Seat has PC | PC after partner |
| 4 | Seat has OC | OC after opponents |
| 5 | Remaining | Clockwise fill |

**Risk weighting** for multiple subprofiles:
- Risk factors: Standard=0, RS=1.0, PC=0.5, OC=0.5
- Seat risk = Σ (normalized_weight × risk_factor)
- Higher risk = higher priority; equal risk = clockwise tiebreaker

Location: `_base_smart_hand_order()` in `wizard_flow.py`

Helpers:
- `_clockwise_from(seat)` - seats clockwise from given seat
- `_detect_seat_roles(seat_profiles)` - RS/PC/OC roles + risk per seat
- `_normalize_subprofile_weights(sub_profiles)` - N subprofiles → 1/N weights
- `_get_subprofile_type(sub)` - classifies as standard/rs/pc/oc
- `_compute_seat_risk(seat_profile)` - weighted risk calculation

Tests: 56 tests in `test_default_dealing_order.py`

## Debug Hooks

```python
_DEBUG_ON_MAX_ATTEMPTS(...)              # Called on exhaustion
_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION(...) # Called on each failed attempt
```

## Key Functions

### deal_generator.py
```python
# Main entry + v1
generate_deals(setup, profile, num_deals, enable_rotation) -> DealSet
_build_single_constrained_deal(rng, profile, board_number, debug) -> Deal
_choose_hardest_seat_for_board(...) -> Optional[Seat]
_extract_standard_suit_minima(profile, seat, subprofile) -> Dict[str, int]
_construct_hand_for_seat(rng, deck, min_suit_counts) -> List[Card]

# v2 shape help system
_build_single_constrained_deal_v2(rng, profile, board_number) -> Deal
_select_subprofiles_for_board(rng, profile, dealing_order) -> (subs, indices)
_pre_select_rs_suits(rng, chosen_subs) -> Dict[Seat, List[str]]
_dispersion_check(chosen_subs, threshold, rs_pre_selections) -> set[Seat]
_deal_with_help(rng, deck, subs, tight_seats, order, rs_pre_selections) -> (Dict[Seat, List[Card]], None) | (None, Seat)
_pre_allocate(rng, deck, subprofile, fraction) -> List[Card]
_pre_allocate_rs(rng, deck, subprofile, pre_selected_suits, fraction) -> List[Card]
_random_deal(rng, deck, n) -> List[Card]
_card_hcp(card) -> int
_deck_hcp_stats(deck) -> (hcp_sum, hcp_sum_sq)
_check_hcp_feasibility(drawn_hcp, cards_remaining, deck_size, ...) -> bool
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

## Test Coverage

**414 tests (414 passed, 4 skipped)** organized by:
- Core matching: `test_seat_viability*.py`
- Constructive help: `test_constructive_*.py`, `test_hardest_seat_*.py`
- Nonstandard: `test_random_suit_*.py`
- Index coupling: `test_f3_opener_responder_coupling.py`, `test_ew_index_coupling.py`
- Profile viability: `test_profile_viability_*.py`
- Benchmarks: `test_profile_e_*.py`
- **v3 shape help**: `test_shape_help_v3.py` (75 tests — D1-D7)
- **HCP feasibility**: `test_hcp_feasibility.py` (36 tests — unit + integration)
- **Profile E e2e**: `test_profile_e_v2_hcp_gate.py` (7 tests — v2 builder + pipeline)
- **RS pre-selection**: `test_rs_pre_selection.py` (32 tests — B1-B4 unit tests)
- **Defense to Weak 2s**: `test_defense_weak2s_diagnostic.py` (2 tests — diagnostic + pipeline)
- **v2 comparison**: `test_v2_comparison.py` (6 gated — `RUN_V2_BENCHMARKS=1`)

**Untested modules** (low risk):
- `profile_convert.py` - file I/O logic (should add tests)
- `profile_print.py`, `wizard_constants.py`, `cli_prompts.py`, `menu_help.py` - minimal/static

---

## Known Structural Issues

### Duplicate Definitions (need cleanup)

| File | Issue |
|------|-------|
| `hand_profile_model.py` | `SubProfile` class x2 |
| `orchestrator.py` | `_format_nonstandard_rs_buckets()` x2 — *removed in #4b* |
| `profile_cli.py` | `draft_tools_action()` x2 |

*Resolved*: `_weights_for_seat_profile()`, `_choose_index_for_seat()`, `_select_subprofiles_for_board()` — duplicates cleaned up.

### Orphaned/Dead Code

| File | Issue |
|------|-------|
| `hand_profile_model.py` | Orphaned `from_dict()` at module level |
| `orchestrator.py` | Unreachable try-except |
*Resolved*: `_build_rs_bucket_snapshot()`, `_nonstandard_constructive_help_enabled()`, v2 nonstandard stubs, `ENABLE_CONSTRUCTIVE_HELP` flags, debug hooks — removed.

*Resolved*: Cascading dead code: `_shadow_probe_nonstandard_constructive()`, `_nonstandard_constructive_v2_policy()`, `_build_constraint_flags_per_seat()`, inline PC/OC nudge blocks, RS bucket tracking, shadow functions in orchestrator.py — removed.

*Resolved*: `passrandom_suit_choices` merge artifact — cleaned up.

### Missing Implementations

| File | Issue |
|------|-------|
| `profile_store.py` | `list_drafts()` called but not defined |
