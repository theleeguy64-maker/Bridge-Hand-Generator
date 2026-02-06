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
Build Deck + Deal Hands
    ↓
Match Each Seat (RS seats first, then others)
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
- Constrained deal generation with retry loop (v1 active path)
- v2 shape-based help system (D0-D6 complete, parallel to v1)
- Profiles A-D work with v2 (tight shape constraints handled)
- Base Smart Hand Order algorithm for optimal dealing order
- Local failure attribution with rotation benchmarks
- 353 tests passing, 4 skipped

### Remaining Work
1. **Full attribution in v2** (D7) — add seat_fail counters + debug hooks
2. **Comparative benchmarks** (D8) — gated v1 vs v2 tests
3. **Swap v2 into main loop** (D9) — one-line change
4. **HCP help** — extend pre-allocation to bias card selection for tight HCP
5. Profile E (6 spades + 10-12 HCP) still too hard — needs HCP help

## Design Principles

1. **Separate viability from strategy** - First decide if profile is possible, then worry about how to generate
2. **Local, not global attribution** - Pin failures on specific seats, not smeared across all
3. **Data-driven decisions** - Prove which seat needs help via experiments, don't hardcode
4. **Conservative help** - Constructive should only make hard things easier, never break correctness

## Key Files

| File | Purpose |
|------|---------|
| `deal_generator.py` | Main pipeline, v1 + v2 shape help, failure attribution |
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
