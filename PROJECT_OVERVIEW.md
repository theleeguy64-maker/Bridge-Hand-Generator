# Bridge Hand Generator - Project Overview

## Purpose

Generate bridge card deals that satisfy complex constraint profiles. The system must:
1. **Validate profiles** - Fail fast on mathematically impossible constraints
2. **Generate deals** - Build 4-hand deals satisfying all seat constraints
3. **Help intelligently** - Pre-allocate cards for seats with tight shape constraints
4. **Be diagnosable** - Provide stats explaining why profiles are hard or failing

## Core Problem

Given a `HandProfile` describing what each seat's hand should look like (HCP ranges, suit lengths, contingent constraints), generate valid deals or fail loudly when impossible.

## Key Concepts

### Constraint Types

| Type | Description | Example |
|------|-------------|---------|
| **Standard** | Per-suit min/max cards + HCP, total HCP | "5+ spades, 12-14 HCP" |
| **Random Suit (RS)** | Choose N suits from allowed set, each satisfying a range | "Pick 2 majors with 4+ cards" |
| **Partner Contingent (PC)** | Constraint depends on partner's RS choice | "If partner has long spades, I need 3+ spades" |
| **Opponent Contingent (OC)** | Constraint depends on opponent's RS choice | "If RHO has long diamonds, I need diamond stopper" |

### The Pipeline

```
Profile Viability (Stage 0-2)
    ↓ (pass)
Deal Generation Loop
    ↓
Select Subprofiles (with NS/EW index coupling)
    ↓
Pre-select RS suits (make RS visible to help system)
    ↓
Build Deck + Deal Hands (with shape help + RS pre-allocation)
    ↓
Match Each Seat (RS seats first, using pre-committed suits)
    ↓
Success → Return Deal | Failure → Retry (up to 10,000 attempts)
```

### Shape-Based Help System (v2 — The Core Innovation)

**Key insight**: Select subprofiles FIRST, then use a probability table to identify
which seats have tight shape constraints and pre-allocate some of their required cards.

**Pipeline:**
```
Select subprofiles for board (weighted random, with NS/EW coupling)
    ↓
Dispersion check → identify tight seats (P(>=min_cards) ≤ 19%)
    ↓
Deal with help:
  - Tight seats: pre-allocate 75% of standard suit minima (100% for RS suits with HCP targeting)
  - Non-tight seats: constrained fill (respects suit max + HCP max)
  - Last seat: gets pre-allocated + remainder
    ↓
Match all seats → Success or retry
```

**Why it works**: If North needs 6+ spades, random dealing has only 6.3% chance
of delivering that. Pre-allocating 5 spades (75%) gives North a head start,
dramatically reducing retry attempts. RS suits get 100% pre-allocation with
HCP targeting to satisfy tight suit-level HCP windows.

### Failure Attribution

Per-attempt tracking for diagnostics:
- `seat_fail_as_seat` → "This seat actually failed"
- `seat_fail_global_other` → "This seat passed; someone else failed"
- `seat_fail_global_unchecked` → "Never got checked due to early termination"

## Current State

### What Works
- Profile validation and viability checking
- Constrained deal generation with retry loop (v2 active path, v1 available for rollback)
- v2 shape-based help system (D0-D9 complete, production path)
- RS-aware pre-selection (#8): RS suits pre-selected before dealing, visible to dispersion check and pre-allocation
- Profiles A-E all work with v2 (tight shape + HCP constraints handled)
- "Defense to 3 Weak 2s" profile generates 6 boards in ~1.5s (full RS pre-allocation #14; was ~50s before, was unviable before #8)
- HCP feasibility rejection (#5): early rejection of hands with infeasible HCP after pre-allocation
- Profile E (6 spades + 10-12 HCP) generates successfully end-to-end
- 3-phase `_deal_with_help`: all tight seats (including last) get pre-allocation
- Local failure attribution with rotation benchmarks
- Dead code cleanup complete (#4, #4b): removed stubs, flags, hooks, cascading dead code
- Performance optimizations (#10): master deck constant, index-based dealing, suit pre-indexing, incremental HCP, unrolled matching (~19% faster)
- Constrained fill (#11): suit max + HCP max enforcement during dealing, PRE_ALLOCATE_FRACTION 0.75 — W shape failures eliminated, HCP failures -81%
- Full RS pre-allocation (#14): RS_PRE_ALLOCATE_FRACTION=1.0 — RS suits fully populated at pre-allocation time with HCP targeting. "Defense to Weak 2s" 5-20x faster
- Adaptive re-seeding (#12): per-board timing + auto re-seed on slow boards (1.75s threshold) — eliminates seed-dependent variance
- 444 tests passing

### Remaining Work
- **Benchmark suite** — establish baseline performance metrics across test profiles (A-E + production profiles) to track v2 optimization impact
- **Profile review** — audit all 11 profiles for correct constraints, metadata, and dealing order

## Design Principles

1. **Separate viability from strategy** - First decide if profile is possible, then worry about how to generate
2. **Local, not global attribution** - Pin failures on specific seats, not smeared across all
3. **Data-driven decisions** - Prove which seat needs help via experiments, don't hardcode
4. **Conservative help** - Constructive should only make hard things easier, never break correctness

## Key Files

| File | Lines | Purpose |
|------|-------|---------|
| `deal_generator.py` | 384 | Facade: subprofile selection + `generate_deals()` + re-exports |
| `deal_generator_v2.py` | 1,229 | v2 shape-help helpers + v2 builder (active production path) |
| `deal_generator_v1.py` | 782 | v1 builder + hardest-seat + constructive help (legacy, rollback only) |
| `deal_generator_types.py` | 285 | Types, constants, dataclasses, exception, debug hooks (leaf module) |
| `deal_generator_helpers.py` | 462 | Shared utilities: viability, HCP, deck helpers, vulnerability/rotation |
| `hand_profile_model.py` | 775 | Data models: SubProfile, SeatProfile, HandProfile |
| `seat_viability.py` | 589 | Constraint matching: `_match_seat`, `_match_subprofile`, RS pre-selection |
| `hand_profile_validate.py` | 512 | Profile validation |
| `profile_viability.py` | 371 | Profile-level viability + cross-seat feasibility checks |
| `wizard_flow.py` | 1,340 | Wizard steps, seat editing |
| `profile_cli.py` | 867 | Profile commands (atomic saves) |
| `orchestrator.py` | 485 | CLI/session management + generic menu loop |
| `profile_store.py` | 302 | JSON persistence (atomic writes, error-tolerant loading, display ordering) |
| `failure_report.py` | 275 | Failure attribution diagnostic (uses v2 builder) |

## Terminology

- **Seat**: N, E, S, W
- **SubProfile**: One constraint configuration for a seat
- **SeatProfile**: List of SubProfiles (alternatives) for a seat
- **HandProfile**: Complete profile with all seats + metadata
- **Dealing Order**: Which seat gets cards first (affects attribution)
- **NS/EW Coupling**: Partners use same subprofile index
- **Driver/Follower**: Which partner's index choice drives the coupling
