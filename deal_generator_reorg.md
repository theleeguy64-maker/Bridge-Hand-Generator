# Deal Generator Reorganization - Complete Story

## The Problem

When a profile has tight shape constraints (like "North needs 6 spades"), random dealing is inefficient. The system shuffles and deals thousands of times before North randomly gets 6 spades. Meanwhile, the other three seats with loose constraints pass easily every time.

The old "constructive help" system was:
- Hardcoded OFF (never runs)
- Complex 5-gate logic that asked wrong questions
- Couldn't help multiple seats
- Couldn't identify which seats needed help

---

## The Solution

**Key insight:** Select subprofiles FIRST, then we know exactly what constraints we're dealing with. No guessing.

**Simple question:** Which seats have tight shape constraints? Help those seats by pre-allocating some cards of the suits they need.

---

## The Two Loops

### Outer Loop (Per Board)

For each board we want to generate:

1. **Pick subprofiles** - Select which subprofile each seat uses (weighted random). This is LOCKED for this board.

2. **Find tight seats** - Check each seat's shape constraints. If any suit requires 5+ cards (probability ≤ 19%), that seat is "tight" and needs help.

3. **Run inner loop** - Try to deal a valid hand.

4. **Record success** - Move to next board.

### Inner Loop (Per Attempt)

Within a single board (same constraints):

1. **Shuffle deck** - Fresh 52-card deck.

2. **Deal cards** - For each seat in dealing order:
   - If seat is tight: Pre-allocate 50% of suit minima, fill rest randomly
   - If seat is not tight: Deal 13 random cards
   - Last seat: Gets remainder (always 13)

3. **Check constraints** - Verify each hand matches its subprofile.

4. **If match** - Success! Exit inner loop.

5. **If fail** - Retry with new shuffle (same constraints).

6. **If exhausted** - Error after 10,000 attempts.

---

## Dispersion Check

**Purpose:** Find which seats have tight shape constraints.

**Input:** The chosen subprofiles for all four seats.

**Output:** Set of seats that need help (could be empty, one seat, or multiple).

**Logic:** For each seat, check each suit's min_cards. Look up the probability in the shape table. If probability ≤ 19%, add seat to the tight set.

**Examples:**
- North needs 5+ spades (19%) → {North}
- North needs 6+ spades (6%) → {North}
- North needs 6+ spades, South needs 5+ hearts → {North, South}
- All seats need 0+ cards → {} (empty, no help needed)

---

## Shape Probability Table

Probability of a random 13-card hand having at least N cards in a specific suit:

| min_cards | probability | needs help? |
|-----------|-------------|-------------|
| 0 | 100% | No |
| 1 | 98.7% | No |
| 2 | 92% | No |
| 3 | 71% | No |
| 4 | 43% | No |
| 5 | 19% | **Yes** (at threshold) |
| 6 | 6.3% | **Yes** |
| 7 | 2.1% | **Yes** |
| 8+ | <1% | **Yes** |

Threshold is 19% (configurable). Anything at or below gets help.

---

## Pre-Allocation

**Purpose:** Give tight seats a head start on their required suits.

**Strategy:** Allocate 50% of the minimum cards required (rounded down).

**Examples:**
- Needs 6 spades → Pre-allocate 3 spades
- Needs 5 hearts → Pre-allocate 2 hearts
- Needs 4 diamonds → Pre-allocate 2 diamonds
- Needs 1 club → Pre-allocate 0 clubs (50% of 1 rounds to 0)

**Why 50%?** Balance between helping enough and not over-constraining the deck. If we gave all 6 spades upfront, the remaining deck would be depleted of spades, potentially causing problems for other seats.

**Process:**
1. For each suit with min_cards > 0:
   - Calculate: to_allocate = floor(min_cards × 0.50)
   - Pick that many random cards of that suit from deck
   - Remove them from deck
2. Return all pre-allocated cards
3. Fill remaining slots (13 - pre_allocated) with random cards

---

## Dealing With Help

For each seat in dealing_order:

**If seat is in tight_seats:**
1. Pre-allocate cards for tight suits
2. Fill to 13 with random cards from remaining deck

**If seat is NOT in tight_seats:**
1. Deal 13 random cards from deck

**Last seat (always):**
1. Gets whatever remains (always exactly 13 cards)

---

## What About HCP?

This version only helps with **shape** constraints (cards in suit).

**HCP help is a future TODO.** The challenge: we can't just "give high cards" without also affecting shape. Need a smarter approach.

For now, tight HCP constraints (like 10-12 HCP) will still rely on random dealing and retries.

---

## Configuration

| Parameter | Default | Purpose |
|-----------|---------|---------|
| SHAPE_PROB_THRESHOLD | 0.19 | Probability cutoff (≤19% needs help) |
| PRE_ALLOCATE_PERCENT | 0.50 | Fraction of suit minima to pre-allocate |

Both are configurable, not hardcoded.

---

## Test Profiles (Progressive Difficulty)

| Profile | North Constraint | Shape Prob | Tight? |
|---------|------------------|------------|--------|
| A | None | 100% | No |
| B | 5+ spades | 19% | Yes (borderline) |
| C | 10-12 HCP only | 100% | No (HCP not helped yet) |
| D | 5+ spades + 10-12 HCP | 19% | Yes (shape) |
| E | 6 spades + 10-12 HCP | 6% | Yes (shape) |

---

## What Gets Built

### New Functions

1. **SHAPE_PROB_GTE** - Lookup table for shape probabilities

2. **dispersion_check(chosen_subs)** → Set[Seat]
   - Returns set of seats with tight shape constraints

3. **random_deal(rng, deck, n)** → List[Card]
   - Deal n random cards, mutate deck

4. **pre_allocate(rng, deck, subprofile)** → List[Card]
   - Pre-allocate 50% of suit minima, mutate deck

5. **deal_with_help(rng, deck, chosen_subs, tight_seats, dealing_order)** → Dict[Seat, List[Card]]
   - Main dealing function that uses pre-allocation for tight seats

6. **_build_single_constrained_deal_v2()** ← NEW FUNCTION
   - Complete new deal builder with help system
   - Old function stays untouched

---

## Integration Strategy (Option B - New Function)

Instead of modifying existing code, create a parallel function:

```
_build_single_constrained_deal()      ← untouched, existing tests pass
_build_single_constrained_deal_v2()   ← new code with help system
```

**Why this is lowest risk:**
1. Old code literally untouched
2. Existing tests keep passing throughout development
3. New function can be tested in complete isolation
4. Integration tests call v2 directly
5. When v2 is proven: one-line change swaps which function main loop calls
6. Easy rollback: swap back to original function

**The swap (when ready):**
```python
# In generate_deals() or wherever the loop is:
# Before:
deal = _build_single_constrained_deal(...)

# After:
deal = _build_single_constrained_deal_v2(...)
```

---

## Risk Assessment

| # | Element | Risk | Why |
|---|---------|------|-----|
| 1 | SHAPE_PROB_GTE table | Very Low | Just a constant dict |
| 2 | dispersion_check() | Low | Pure function, no mutation |
| 3 | random_deal() | Low | Simple, mutates deck |
| 4 | pre_allocate() | Medium | Multiple suits, rounding |
| 5 | deal_with_help() | Medium | Orchestrates others |
| 6 | _build_single_constrained_deal_v2() | Low | NEW function, old untouched |
| 7 | Swap to v2 | Low | One-line change, easy rollback |

**Implementation order (lowest risk first):**
1. SHAPE_PROB_GTE + tests
2. dispersion_check() + tests
3. random_deal() + tests
4. pre_allocate() + tests
5. deal_with_help() + tests
6. _build_single_constrained_deal_v2() + tests
7. Integration tests with failure_report
8. Swap main loop to v2

---

## What Gets Reused

**Call but don't modify:**
- `_match_seat()` / `_match_subprofile()` - for constraint checking

**Don't touch:**
- `_build_single_constrained_deal()` - OLD FUNCTION STAYS UNCHANGED

---

## What Gets Deleted (Later)

After v2 is proven AND swapped in:
- `ENABLE_CONSTRUCTIVE_HELP = False`
- `ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD = False`
- Old 5-gate logic
- `_is_shape_dominant_failure()`
- `_extract_standard_suit_minima()` bounds check
- Eventually `_build_single_constrained_deal()` (old version)

---

## Process Metrics

**Decision:** Use probability tables (SHAPE_PROB_GTE) to determine who needs help

**Validation:** Use existing `failure_report.py` to measure actual performance

**failure_report.py provides:**
- `seat_fail_as_seat` - which seat failed first
- `seat_fail_shape` - shape failures per seat
- `seat_fail_hcp` - HCP failures per seat
- `pain_share` - fraction of failures per seat
- `hardest_seat` - the bottleneck

**Testing approach:**
1. Run Profile E WITHOUT help (old code) → get baseline report
2. Run Profile E WITH help (v2 code) → get improved report
3. Compare: attempts, pain_share, hardest_seat

---

## Unit Tests

### Probability Table
- Verify SHAPE_PROB_GTE[5] ≈ 0.189
- Verify SHAPE_PROB_GTE[6] ≈ 0.063
- Verify table has entries 0-13

### dispersion_check()
- Loose profile → empty set
- 5+ cards in one seat → {that seat}
- 6+ cards in two seats → {both seats}
- Edge: exactly at threshold

### random_deal()
- Deals n cards
- Mutates deck (removes dealt cards)
- Handles n > deck size
- Returns empty for n = 0

### pre_allocate()
- 6 min → 3 allocated
- 5 min → 2 allocated
- 1 min → 0 allocated
- Multiple suits handled
- Deck mutated correctly

### deal_with_help()
- Tight seats get pre-allocation
- Non-tight seats get random 13
- Last seat gets remainder
- Total = 52 cards
- No duplicate cards

---

## Integration Tests

**Using failure_report.py for validation:**

### Profile A (Loose) - Baseline
- dispersion_check returns empty set
- No pre-allocation happens
- Low attempt count in failure report

### Profile E - Compare Old vs New
- Run with `_build_single_constrained_deal()` (old) → baseline report
- Run with `_build_single_constrained_deal_v2()` (new) → improved report
- Compare:
  - Total attempts (should decrease)
  - pain_share for North (should decrease)
  - hardest_seat (may change or stay same)

### Multiple Tight Seats
- Create profile with North (6 spades) + South (5 hearts)
- dispersion_check returns {North, South}
- Both get pre-allocation
- Compare failure reports

---

## Performance Tests

- Generate 100 boards with Profile A (baseline)
- Generate 100 boards with Profile E (with help)
- Compare: attempt counts, total time
- Help should reduce attempts for tight profiles
- Help should not slow down loose profiles significantly

---

## Future TODOs

- **HCP help**: Pre-allocate high cards for seats with tight HCP constraints
- **Adaptive pre-allocation**: Increase percentage on repeated failures (33% → 50% → 66%)

---

## Files to Modify

- `bridge_engine/deal_generator.py` - Add new functions, wire into loop
- `tests/test_constructive_help_v3.py` - New test file
