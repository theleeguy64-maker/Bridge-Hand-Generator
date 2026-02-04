# Bridge Hand Generator - Project Overview

## Purpose

Generate bridge card deals that satisfy complex constraint profiles. The system must:
1. **Validate profiles** - Fail fast on mathematically impossible constraints
2. **Generate deals** - Build 4-hand deals satisfying all seat constraints
3. **Help intelligently** - Use constructive dealing only for the actual bottleneck seat
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

### Helper Seat Selection (The Core Innovation)

**Old approach**: Global failure stats mixing direct failures with collateral damage.

**New approach**: Local, per-attempt attribution:
- `seat_fail_as_seat` → "This seat actually failed" (used for helper selection)
- `seat_fail_global_other` → "This seat passed; someone else failed"
- `seat_fail_global_unchecked` → "Never got checked due to early termination"

**Decision rule**: The seat with the highest `seat_fail_as_seat` share (≥25%, ≥2× others) is the helper seat.

### Constructive Dealing

When a helper seat is identified:
1. Extract suit minima from its constraints
2. Build hand satisfying those minima first
3. Fill remaining cards randomly
4. This makes the hard seat easier to satisfy

**v1 (Standard)**: Only for "standard" seats with simple suit minima.
**v2 (Nonstandard)**: Experimental - RS reordering, PC/OC nudging.

## Current State

### What Works
- Profile validation and viability checking
- Constrained deal generation with retry loop
- Local failure attribution with rotation benchmarks
- Profile E benchmark proves North is the bottleneck (~95% of failures)

### The Gap
- v1 constructive has 4 gates that prevent it from firing for Profile E
- The "standard vs nonstandard" distinction is the wrong axis
- Real question: "Is this seat constrained enough, and failing in ways constructive can help?"

### Pending Work
1. Relax v1 gates so constructive actually fires for identified helper seats
2. Complete HCP vs shape failure classification
3. Add "too hard = unviable" declaration when success probability is negligible

## Design Principles

1. **Separate viability from strategy** - First decide if profile is possible, then worry about how to generate
2. **Local, not global attribution** - Pin failures on specific seats, not smeared across all
3. **Data-driven decisions** - Prove which seat needs help via experiments, don't hardcode
4. **Conservative help** - Constructive should only make hard things easier, never break correctness

## Key Files

| File | Purpose |
|------|---------|
| `deal_generator.py` | Main pipeline, constructive help, failure attribution |
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
