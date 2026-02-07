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
  - Tight seats: pre-allocate 50% of suit minima, fill rest randomly
  - Non-tight seats: deal 13 random cards
  - Last seat: gets remainder
    ↓
Match all seats → Success or retry
```

**Why it works**: If North needs 6+ spades, random dealing has only 6.3% chance
of delivering that. Pre-allocating 3 spades gives North a head start, dramatically
reducing retry attempts.

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
- "Defense to 3 Weak 2s" profile generates 6 boards in ~50s via board-level retry (#9)
- HCP feasibility rejection (#5): early rejection of hands with infeasible HCP after pre-allocation
- Profile E (6 spades + 10-12 HCP) generates successfully end-to-end
- 3-phase `_deal_with_help`: all tight seats (including last) get pre-allocation
- Base Smart Hand Order algorithm for optimal dealing order
- Local failure attribution with rotation benchmarks
- Dead code cleanup complete (#4, #4b): removed stubs, flags, hooks, cascading dead code
- Performance optimizations (#10): master deck constant, index-based dealing, suit pre-indexing, incremental HCP, unrolled matching (~19% faster)
- Constrained fill (#11): suit max + HCP max enforcement during dealing, PRE_ALLOCATE_FRACTION 0.75 — W shape failures eliminated, HCP failures -81%
- 414 tests passing, 4 skipped

### Remaining Work
1. **Refactor large files** (#7) — Batches 1-2 done: deal_generator.py 2,678→2,122 + types (230) + helpers (444). Batches 3-5 pending (v1, v2, cleanup). Also: hand_profile_model.py (921), profile_cli.py (968)

## Design Principles

1. **Separate viability from strategy** - First decide if profile is possible, then worry about how to generate
2. **Local, not global attribution** - Pin failures on specific seats, not smeared across all
3. **Data-driven decisions** - Prove which seat needs help via experiments, don't hardcode
4. **Conservative help** - Constructive should only make hard things easier, never break correctness

## Key Files

| File | Purpose |
|------|---------|
| `deal_generator.py` | Facade + v1/v2 builders + generate_deals() + subprofile selection |
| `deal_generator_types.py` | Types, constants, dataclasses, exception, debug hooks (leaf module) |
| `deal_generator_helpers.py` | Shared utilities: viability, HCP, deck helpers, vulnerability/rotation |
| `hand_profile_model.py` | Data models: SubProfile, SeatProfile, HandProfile |
| `seat_viability.py` | Constraint matching: _match_seat, _match_subprofile |
| `hand_profile_validate.py` | Profile validation |
| `profile_viability.py` | Profile-level viability checks |

## Terminology

- **Seat**: N, E, S, W
- **SubProfile**: One constraint configuration for a seat
- **SeatProfile**: List of SubProfiles (alternatives) for a seat
- **HandProfile**: Complete profile with all seats + metadata
- **Dealing Order**: Which seat gets cards first (affects attribution)
- **NS/EW Coupling**: Partners use same subprofile index
- **Driver/Follower**: Which partner's index choice drives the coupling
