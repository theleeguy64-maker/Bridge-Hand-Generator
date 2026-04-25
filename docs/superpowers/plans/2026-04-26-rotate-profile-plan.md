# Rotate Profile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tool that produces a rotated copy of a hand profile (W→N→E→S→W) — same hand-shape constraints, seats relabelled. Available both as a CLI (`python -m bridge_engine.rotate_profile`) and as an Admin submenu entry.

**Architecture:** One new module `bridge_engine/rotate_profile.py` containing a pure `rotate_profile(profile_dict) -> dict` function, an interactive menu entry `run_rotation_menu()`, and a `main(argv)` CLI entry. One small change to `bridge_engine/orchestrator.py` to wire the menu entry. Reuses existing `profile_store._slugify`/`_atomic_write`, `profile_cli._safe_file_stem`, `hand_profile_validate.validate_profile`, and `HandProfile.from_dict` — no new infrastructure.

**Tech Stack:** Python 3.13, pytest, ruff, pyright. The project layout is `bridge_engine/` (package) + `tests/` (pytest) + `profiles/` (JSON profiles). Tests run via `.venv/bin/pytest -v`.

---

## File Structure

**Create:**
- `bridge_engine/rotate_profile.py` — module with `ROTATE_MAP`, helper functions, `rotate_profile()`, `run_rotation_menu()`, `main()`.
- `tests/test_rotate_profile.py` — unit tests for the pure function and helpers.
- `tests/test_rotate_profile_cli.py` — CLI exit-code tests using `main(argv)` injection.
- `tests/test_rotate_profile_integration.py` — integration tests that read real `profiles/*.json`.
- `tests/conftest.py` — *modify only* to add a `make_profile_dict` fixture if the file exists; create it if not.

**Modify:**
- `bridge_engine/orchestrator.py` — add one entry to `admin_menu()`.

---

## Sanity check before starting

- [ ] **Step 0a: Confirm baseline tests pass and pyright is clean**

Run: `.venv/bin/pytest -q && npx pyright bridge_engine/`

Expected: `578 passed` (or more), `0 errors`. If either fails, stop — fix the baseline first; don't pile a new feature on top of a broken tree.

- [ ] **Step 0b: Verify there's no existing `tests/conftest.py`**

Run: `ls tests/conftest.py 2>/dev/null || echo "no conftest"`

Expected: either prints the path (existing — we'll add to it) or `no conftest` (we'll create it). Note which one and use it later.

---

## Task 1: Module skeleton and ROTATE_MAP

**Files:**
- Create: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

- [ ] **Step 1.1: Write the failing test for `_rotate_seat`**

Create `tests/test_rotate_profile.py`:

```python
"""Tests for bridge_engine.rotate_profile."""
from __future__ import annotations

import pytest

from bridge_engine.rotate_profile import ROTATE_MAP, _rotate_seat


def test_rotate_seat_map():
    assert ROTATE_MAP == {"W": "N", "N": "E", "E": "S", "S": "W"}
    assert _rotate_seat("W") == "N"
    assert _rotate_seat("N") == "E"
    assert _rotate_seat("E") == "S"
    assert _rotate_seat("S") == "W"


def test_rotate_seat_rejects_bad_input():
    with pytest.raises(ValueError):
        _rotate_seat("X")
    with pytest.raises(ValueError):
        _rotate_seat("")
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: collection error / `ModuleNotFoundError: No module named 'bridge_engine.rotate_profile'`.

- [ ] **Step 1.3: Create the minimal module**

Create `bridge_engine/rotate_profile.py`:

```python
"""Rotate a HandProfile around the table (W→N→E→S→W).

Pure data transformation: every seat reference advances one position around
the cycle. See docs/superpowers/specs/2026-04-25-rotate-profile-design.md
for the full rule set.
"""
from __future__ import annotations

ROTATE_MAP: dict[str, str] = {"W": "N", "N": "E", "E": "S", "S": "W"}


def _rotate_seat(seat: str) -> str:
    if seat not in ROTATE_MAP:
        raise ValueError(f"Invalid seat: {seat!r}")
    return ROTATE_MAP[seat]
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: 2 passed.

- [ ] **Step 1.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile.py
git commit -m "rotate_profile: module skeleton + _rotate_seat"
```

---

## Task 2: Profile-dict fixture

**Files:**
- Create or modify: `tests/conftest.py` (depends on Step 0b result).
- Test: `tests/test_rotate_profile.py` (smoke check the fixture).

The fixture is shared across the unit-test files. Putting it in `conftest.py` means later tests can just declare `make_profile_dict` as a parameter without imports.

- [ ] **Step 2.1: Add the fixture**

`tests/conftest.py` already exists (verified at Step 0b). It already imports `pytest` and `copy`, and has a `from __future__ import annotations` line at the top. **Append only the new symbols** — do NOT re-add `from __future__ import annotations`, `import pytest`, or any duplicate imports. The only new top-level import you need is `from typing import Any` (verify whether it's already present; add only if missing). Then append the two new symbols (`_canonical_profile_dict` and `make_profile_dict`) to the bottom of the file. Use `copy.deepcopy(...)` (matches the existing file's style — it uses `import copy`, not `from copy import deepcopy`).

```python
# Append to existing tests/conftest.py — do NOT re-add `from __future__`,
# `import pytest`, or `import copy` (already present). Add `from typing import Any`
# at the top only if not already imported.


def _canonical_profile_dict() -> dict[str, Any]:
    """A canonical HandProfile-shaped dict exercising every field touched
    by the rotation rules. Deep-copy via the fixture before mutating."""
    return {
        "profile_name": "Opps Open 1NT and we Overcall",
        "description": "Opps open 1NT, we overcall",
        "category": "We Compete",
        "author": "Lee",
        "tag": "Overcaller",
        "version": "1.0",
        "schema_version": 1,
        "sort_order": 5,
        "dealer": "W",
        "hand_dealing_order": ["W", "N", "E", "S"],
        "rotate_deals_by_default": True,
        "is_invariants_safety_profile": False,
        "subprofile_exclusions": [
            {"seat": "W", "subprofile_index": 1},
            {"seat": "E", "subprofile_index": 2},
        ],
        "ns_linked_profile": {
            "primary_seat": "N",
            "subprofile_map": {"1": [1], "2": [1, 2]},
        },
        "ew_linked_profile": {
            "primary_seat": "E",
            "subprofile_map": {"1": [1]},
        },
        "seat_profiles": {
            seat: {
                "seat": seat,
                "subprofiles": [
                    {
                        "name": "Balanced",
                        "weight_percent": 100.0,
                        "standard": {
                            "clubs": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "diamonds": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "hearts": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "spades": {"min_cards": 0, "max_cards": 5, "min_hcp": 0, "max_hcp": 8},
                            "total_min_hcp": 6,
                            "total_max_hcp": 10,
                        },
                        "random_suit_constraint": None,
                        "partner_contingent_constraint": (
                            {"partner_seat": "S", "use_non_chosen_suit": False,
                             "suit_range": {"min_cards": 4, "max_cards": 6, "min_hcp": 0, "max_hcp": 7}}
                            if seat == "N" else None
                        ),
                        "opponents_contingent_suit_constraint": (
                            {"opponent_seat": "W", "use_non_chosen_suit": True,
                             "suit_range": {"min_cards": 0, "max_cards": 3, "min_hcp": 0, "max_hcp": 8}}
                            if seat == "E" else None
                        ),
                    }
                ],
            }
            for seat in ("N", "E", "S", "W")
        },
    }


@pytest.fixture
def make_profile_dict():
    """Return a factory that produces a fresh deep copy on each call."""
    def _factory() -> dict[str, Any]:
        return deepcopy(_canonical_profile_dict())
    return _factory
```

- [ ] **Step 2.2: Smoke-test the fixture**

Append to `tests/test_rotate_profile.py`:

```python
def test_fixture_factory_returns_independent_dicts(make_profile_dict):
    a = make_profile_dict()
    b = make_profile_dict()
    a["dealer"] = "X"
    assert b["dealer"] == "W"
```

- [ ] **Step 2.3: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: 3 passed.

- [ ] **Step 2.4: Commit**

```bash
git add tests/conftest.py tests/test_rotate_profile.py
git commit -m "rotate_profile: canonical profile-dict fixture"
```

---

## Task 3: `rotate_profile()` — top-level fields and immutability

This task implements the easiest rules first to lock in the function shape. Subprofiles, contingents, linked profiles, and exclusions come in subsequent tasks.

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

- [ ] **Step 3.1: Add tests for top-level rotation + immutability**

Append to `tests/test_rotate_profile.py`:

```python
import copy

from bridge_engine.rotate_profile import rotate_profile


def test_input_dict_not_mutated(make_profile_dict):
    d = make_profile_dict()
    snapshot = copy.deepcopy(d)
    rotate_profile(d)
    assert d == snapshot


def test_dealer_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    assert out["dealer"] == "N"  # source W → N


def test_hand_dealing_order_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    assert out["hand_dealing_order"] == ["N", "E", "S", "W"]  # element-wise


def test_version_reset_to_0_1(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    assert out["version"] == "0.1"


def test_unchanged_top_level_fields(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    for key in ("description", "category", "author", "tag",
                "schema_version", "sort_order",
                "rotate_deals_by_default", "is_invariants_safety_profile"):
        assert out[key] == src[key], f"{key} unexpectedly changed"
```

- [ ] **Step 3.2: Run tests to confirm they fail**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: ImportError on `rotate_profile` (the symbol doesn't exist yet) — collection-time failure.

- [ ] **Step 3.3: Implement `rotate_profile()` covering top-level fields**

Append to `bridge_engine/rotate_profile.py`:

```python
from copy import deepcopy
from typing import Any


_LEGACY_KEYS = ("ns_role_mode", "ew_role_mode", "ns_bespoke_map", "ew_bespoke_map")


def rotate_profile(
    profile_dict: dict[str, Any],
    *,
    new_name: str | None = None,
    new_description: str | None = None,
) -> dict[str, Any]:
    """Return a rotated deep copy of profile_dict.

    The input dict is never mutated. Every seat reference advances one
    position around the cycle W→N→E→S→W. See the module docstring for
    the full rule set.
    """
    out = deepcopy(profile_dict)

    # Top-level seat fields
    if "dealer" in out:
        out["dealer"] = _rotate_seat(out["dealer"])
    if "hand_dealing_order" in out and isinstance(out["hand_dealing_order"], list):
        out["hand_dealing_order"] = [_rotate_seat(s) for s in out["hand_dealing_order"]]

    # Strip legacy keys
    for key in _LEGACY_KEYS:
        out.pop(key, None)

    # Reset version
    out["version"] = "0.1"

    # Subprofiles, exclusions, linked profiles — TODO: subsequent tasks.
    return out
```

- [ ] **Step 3.4: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: all 7 tests pass.

- [ ] **Step 3.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile.py
git commit -m "rotate_profile: top-level fields + immutability + version reset"
```

---

## Task 4: Seat profiles and `subprofile_exclusions`

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

- [ ] **Step 4.1: Add tests**

Append to `tests/test_rotate_profile.py`:

```python
def test_seat_profiles_rekeyed(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    # Source had keys N/E/S/W; each rotates.
    assert set(out["seat_profiles"].keys()) == {"N", "E", "S", "W"}
    # Source W's seat-profile content (its subprofiles) ends up under N.
    src_w = src["seat_profiles"]["W"]
    out_n = out["seat_profiles"]["N"]
    assert out_n["seat"] == "N"  # inner seat field rotated
    assert out_n["subprofiles"] == src_w["subprofiles"]  # subprofile bodies preserved here (rotation of contingents tested separately)
    # Same check for N → E.
    assert out["seat_profiles"]["E"]["seat"] == "E"


def test_subprofile_exclusions_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    # Source had W and E exclusion seats → N and S.
    seats = sorted(e["seat"] for e in out["subprofile_exclusions"])
    assert seats == ["N", "S"]
    # Subprofile indices unchanged.
    indices = sorted(e["subprofile_index"] for e in out["subprofile_exclusions"])
    assert indices == [1, 2]


def test_legacy_fields_stripped(make_profile_dict):
    src = make_profile_dict()
    src["ns_role_mode"] = "stale"
    src["ew_role_mode"] = "stale"
    src["ns_bespoke_map"] = {"1": "stale"}
    src["ew_bespoke_map"] = {"1": "stale"}
    out = rotate_profile(src)
    for key in ("ns_role_mode", "ew_role_mode", "ns_bespoke_map", "ew_bespoke_map"):
        assert key not in out, f"{key} should have been stripped"


def test_unknown_top_level_keys_passthrough(make_profile_dict):
    src = make_profile_dict()
    src["custom_extension"] = {"author_note": "hi"}
    src["future_flag"] = 42
    out = rotate_profile(src)
    assert out["custom_extension"] == {"author_note": "hi"}
    assert out["future_flag"] == 42
```

- [ ] **Step 4.2: Run tests to confirm failure**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: 4 new tests fail (existing seat keys preserved instead of rotated; exclusions seats unchanged; legacy strip + unknown-key passthrough fail because the implementation isn't there yet — the strip code lands here in Step 4.3 and unknown-key passthrough is implicit via deepcopy from Task 3 but needs verification).

Note: legacy-key strip was added in Task 3 (Step 3.3, `_LEGACY_KEYS`); `test_legacy_fields_stripped` will pass already if Task 3 is intact. Unknown-key passthrough is achieved by `deepcopy(profile_dict)` in Task 3 — should already pass. Both tests will go green without Task 4 code changes; they're defensive coverage.

- [ ] **Step 4.3: Implement seat-profile rekey + exclusions rotation**

Edit `bridge_engine/rotate_profile.py` — replace the TODO line in `rotate_profile()` with:

```python
    # seat_profiles: rekey by R(seat), and update inner `seat` field
    if "seat_profiles" in out and isinstance(out["seat_profiles"], dict):
        rekeyed: dict[str, Any] = {}
        for src_seat, sp in out["seat_profiles"].items():
            new_seat = _rotate_seat(src_seat)
            sp["seat"] = new_seat
            rekeyed[new_seat] = sp
        out["seat_profiles"] = rekeyed

    # subprofile_exclusions: rotate each entry's seat
    if "subprofile_exclusions" in out and isinstance(out["subprofile_exclusions"], list):
        for entry in out["subprofile_exclusions"]:
            if isinstance(entry, dict) and "seat" in entry:
                entry["seat"] = _rotate_seat(entry["seat"])

    return out
```

(Replace the existing `return out` line — make sure only one remains.)

- [ ] **Step 4.4: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: all 11 tests pass.

- [ ] **Step 4.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile.py
git commit -m "rotate_profile: seat_profiles rekey + subprofile_exclusions"
```

---

## Task 5: Subprofile contingent seats

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

- [ ] **Step 5.1: Add tests**

Append to `tests/test_rotate_profile.py`:

```python
def test_subprofile_partner_contingent_seat_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    # Source: N's subprofile had partner_seat="S". After rotation, that subprofile
    # lives at E (N→E), and partner_seat S→W.
    sub = out["seat_profiles"]["E"]["subprofiles"][0]
    assert sub["partner_contingent_constraint"]["partner_seat"] == "W"


def test_subprofile_opponent_contingent_seat_rotated(make_profile_dict):
    out = rotate_profile(make_profile_dict())
    # Source: E's subprofile had opponent_seat="W". After rotation, that subprofile
    # lives at S (E→S), and opponent_seat W→N.
    sub = out["seat_profiles"]["S"]["subprofiles"][0]
    assert sub["opponents_contingent_suit_constraint"]["opponent_seat"] == "N"


def test_subprofile_without_contingents_unchanged(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    # Source: S's subprofile had no contingents (only N and E did).
    # After rotation it lives at W. Both contingent fields stay None.
    sub = out["seat_profiles"]["W"]["subprofiles"][0]
    assert sub["partner_contingent_constraint"] is None
    assert sub["opponents_contingent_suit_constraint"] is None
```

- [ ] **Step 5.2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: the partner/opponent contingent tests fail (seats not rotated yet).

- [ ] **Step 5.3: Implement contingent rotation**

Add helper above `rotate_profile()` in `bridge_engine/rotate_profile.py`:

```python
def _rotate_subprofile_contingents(sub: dict[str, Any]) -> None:
    """Rotate seat references inside a single subprofile dict (in place)."""
    pc = sub.get("partner_contingent_constraint")
    if isinstance(pc, dict) and "partner_seat" in pc:
        pc["partner_seat"] = _rotate_seat(pc["partner_seat"])
    oc = sub.get("opponents_contingent_suit_constraint")
    if isinstance(oc, dict) and "opponent_seat" in oc:
        oc["opponent_seat"] = _rotate_seat(oc["opponent_seat"])
```

Then update the seat-profile loop in `rotate_profile()` to call it. Replace the existing seat_profiles block with:

```python
    if "seat_profiles" in out and isinstance(out["seat_profiles"], dict):
        rekeyed: dict[str, Any] = {}
        for src_seat, sp in out["seat_profiles"].items():
            new_seat = _rotate_seat(src_seat)
            sp["seat"] = new_seat
            for sub in sp.get("subprofiles", []):
                if isinstance(sub, dict):
                    _rotate_subprofile_contingents(sub)
            rekeyed[new_seat] = sp
        out["seat_profiles"] = rekeyed
```

- [ ] **Step 5.4: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: all 14 tests pass.

- [ ] **Step 5.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile.py
git commit -m "rotate_profile: rotate contingent seat refs in subprofiles"
```

---

## Task 6: Linked profiles — NS↔EW swap + primary_seat rotation

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

- [ ] **Step 6.1: Add tests**

Append to `tests/test_rotate_profile.py`:

```python
def test_linked_profiles_swap_ns_ew(make_profile_dict):
    src = make_profile_dict()
    out = rotate_profile(src)
    # Source ns had primary N (rotates to E, lives in EW slot now).
    assert out["ew_linked_profile"]["primary_seat"] == "E"
    # Source ew had primary E (rotates to S, lives in NS slot now).
    assert out["ns_linked_profile"]["primary_seat"] == "S"
    # subprofile_map (index-keyed) byte-identical.
    assert out["ew_linked_profile"]["subprofile_map"] == src["ns_linked_profile"]["subprofile_map"]
    assert out["ns_linked_profile"]["subprofile_map"] == src["ew_linked_profile"]["subprofile_map"]


def test_linked_profile_one_none_handled(make_profile_dict):
    src = make_profile_dict()
    src["ew_linked_profile"] = None
    out = rotate_profile(src)
    # Source ns moves to ew slot with primary rotated; ns slot becomes None.
    assert out["ew_linked_profile"] is not None
    assert out["ew_linked_profile"]["primary_seat"] == "E"
    assert out["ns_linked_profile"] is None


def test_linked_profile_both_none_handled(make_profile_dict):
    src = make_profile_dict()
    src["ns_linked_profile"] = None
    src["ew_linked_profile"] = None
    out = rotate_profile(src)
    assert out["ns_linked_profile"] is None
    assert out["ew_linked_profile"] is None
```

- [ ] **Step 6.2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: the 3 new tests fail (linked profiles not yet swapped/rotated).

- [ ] **Step 6.3: Implement linked-profile swap**

Add helper to `bridge_engine/rotate_profile.py`:

```python
def _swap_and_rotate_linked(out: dict[str, Any]) -> None:
    """Swap ns↔ew slots and rotate primary_seat inside each (in place)."""
    ns = out.get("ns_linked_profile")
    ew = out.get("ew_linked_profile")
    if isinstance(ns, dict) and "primary_seat" in ns:
        ns["primary_seat"] = _rotate_seat(ns["primary_seat"])
    if isinstance(ew, dict) and "primary_seat" in ew:
        ew["primary_seat"] = _rotate_seat(ew["primary_seat"])
    out["ns_linked_profile"] = ew
    out["ew_linked_profile"] = ns
```

Then call it inside `rotate_profile()` — add before the `return out` line:

```python
    _swap_and_rotate_linked(out)
```

- [ ] **Step 6.4: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: all 17 tests pass.

- [ ] **Step 6.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile.py
git commit -m "rotate_profile: swap NS↔EW linked profiles + rotate primary_seat"
```

---

## Task 7: Profile-name swap + already-rotated guard

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

- [ ] **Step 7.1: Add tests**

Append to `tests/test_rotate_profile.py`:

```python
from bridge_engine.rotate_profile import _swap_pronouns


@pytest.mark.parametrize("source, expected", [
    ("Opps Open Strong 1NT and we Overcall Cappeletti",
     "We Open Strong 1NT and Opps Overcall Cappeletti"),
    ("Opps Open 3 Weak 2s and we Compete",
     "We Open 3 Weak 2s and Opps Compete"),
    ("Opps Open & Our TO Dbl",
     "We Open & Opps TO Dbl"),
    ("Opps Open & Our TO Dbl Balancing",
     "We Open & Opps TO Dbl Balancing"),
])
def test_swap_pronouns(source, expected):
    assert _swap_pronouns(source) == expected


def test_swap_pronouns_no_pronouns_returns_unchanged():
    # Returns the input verbatim; the rotate_profile() wrapper raises.
    assert _swap_pronouns("Big Hands") == "Big Hands"


def test_rotate_profile_default_name_uses_swap(make_profile_dict):
    src = make_profile_dict()
    src["profile_name"] = "Opps Open 1NT and we Overcall"
    out = rotate_profile(src)
    assert out["profile_name"] == "We Open 1NT and Opps Overcall"


def test_rotate_profile_name_override(make_profile_dict):
    out = rotate_profile(make_profile_dict(), new_name="Custom Name")
    assert out["profile_name"] == "Custom Name"


def test_rotate_profile_description_override(make_profile_dict):
    out = rotate_profile(make_profile_dict(), new_description="Custom desc")
    assert out["description"] == "Custom desc"


def test_rotate_profile_no_pronouns_raises(make_profile_dict):
    src = make_profile_dict()
    src["profile_name"] = "Big Hands"
    from bridge_engine.hand_profile_model import ProfileError
    with pytest.raises(ProfileError, match="Opps/We/Our pronouns"):
        rotate_profile(src)


def test_rotate_profile_already_rotated_refused(make_profile_dict):
    src = make_profile_dict()
    src["rotated_from"] = "earlier.json"
    from bridge_engine.hand_profile_model import ProfileError
    with pytest.raises(ProfileError, match="already a rotated profile"):
        rotate_profile(src)
```

- [ ] **Step 7.2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: ImportError on `_swap_pronouns` and several failures.

- [ ] **Step 7.3: Implement pronoun swap, override hooks, and guards**

Add to `bridge_engine/rotate_profile.py` — first, the imports near the top:

```python
import re

from bridge_engine.hand_profile_model import ProfileError
```

Then add helpers above `rotate_profile()`:

```python
_PRONOUN_PAIRS = (("Our", "We"), ("our", "we"))
_SWAP_PAIRS = (("Opps", "We"), ("opps", "we"))


def _swap_pronouns(name: str) -> str:
    """Two-step pronoun swap on a profile_name string.

    1. Normalise: Our/our → We/we (whole-word).
    2. Swap: Opps↔We, opps↔we (whole-word).
    """
    s = name
    for src, dst in _PRONOUN_PAIRS:
        s = re.sub(rf"\b{src}\b", dst, s)
    for a, b in _SWAP_PAIRS:
        # Use a sentinel so the two replacements don't undo each other.
        sentinel = f"__ROT_{a}__"
        s = re.sub(rf"\b{a}\b", sentinel, s)
        s = re.sub(rf"\b{b}\b", a, s)
        s = s.replace(sentinel, b)
    return s
```

Then update `rotate_profile()` to use it. Replace the existing function body's *opening* (right after the docstring) with:

```python
    # Guard ordering: already-rotated check runs first, so a source with both
    # rotated_from set AND no swappable pronouns still gets the more specific
    # "already rotated" error rather than the generic pronoun message.
    if profile_dict.get("rotated_from"):
        raise ProfileError(
            f"Source is already a rotated profile (rotated_from: "
            f"{profile_dict['rotated_from']!r}); rotation refused."
        )

    out = deepcopy(profile_dict)
```

Then, just before the existing `_swap_and_rotate_linked(out)` call, add:

```python
    # profile_name swap (or override)
    if new_name is not None:
        out["profile_name"] = new_name
    else:
        original = out.get("profile_name", "")
        swapped = _swap_pronouns(original)
        if swapped == original:
            raise ProfileError(
                "Source profile_name does not contain Opps/We/Our pronouns "
                "to swap; supply --name explicitly."
            )
        out["profile_name"] = swapped

    if new_description is not None:
        out["description"] = new_description
```

- [ ] **Step 7.4: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: all 25 tests pass.

- [ ] **Step 7.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile.py
git commit -m "rotate_profile: pronoun swap, name/description overrides, already-rotated guard"
```

---

## Task 8: `rotated_from` provenance + idempotent cycle test

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

`rotated_from` is set by the *I/O layer* (CLI + menu), not the pure function — the pure function doesn't know the source filename. But for the cycle-equivalence check we need the pure function's output to be self-consistent. The full-cycle test runs four rotations on the dict directly, with `profile_name` re-set each iteration to bypass the no-pronouns guard.

- [ ] **Step 8.1: Add cycle test**

Append to `tests/test_rotate_profile.py`:

```python
def test_idempotent_to_full_cycle_seat_fields(make_profile_dict):
    """Four rotations of the seat-bearing fields return to the original."""
    src = make_profile_dict()
    cur = src
    for _ in range(4):
        # Reset profile_name each iteration so the pronoun-swap guard fires
        # only once per cycle. We're testing seat-rotation idempotence here.
        cur = {**cur, "profile_name": src["profile_name"]}
        cur = rotate_profile(cur)
    # After 4 rotations the seat-bearing fields match the source.
    assert cur["dealer"] == src["dealer"]
    assert cur["hand_dealing_order"] == src["hand_dealing_order"]
    assert cur["seat_profiles"].keys() == src["seat_profiles"].keys()
    for seat, sp in src["seat_profiles"].items():
        assert cur["seat_profiles"][seat]["seat"] == sp["seat"]
        assert cur["seat_profiles"][seat]["subprofiles"] == sp["subprofiles"]
    src_excl_sorted = sorted((e["seat"], e["subprofile_index"])
                             for e in src["subprofile_exclusions"])
    cur_excl_sorted = sorted((e["seat"], e["subprofile_index"])
                             for e in cur["subprofile_exclusions"])
    assert cur_excl_sorted == src_excl_sorted
    # Linked profiles return to their original NS/EW positions and primary_seats.
    assert cur["ns_linked_profile"]["primary_seat"] == src["ns_linked_profile"]["primary_seat"]
    assert cur["ew_linked_profile"]["primary_seat"] == src["ew_linked_profile"]["primary_seat"]
```

- [ ] **Step 8.2: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: all 26 tests pass — `rotate_profile()` is functionally complete for the pure function. (No code change needed; this is purely a check.)

- [ ] **Step 8.3: Run pyright + ruff**

Run:

```bash
npx pyright bridge_engine/rotate_profile.py
.venv/bin/ruff check bridge_engine/rotate_profile.py tests/test_rotate_profile.py
.venv/bin/ruff format bridge_engine/rotate_profile.py tests/test_rotate_profile.py
```

Expected: 0 pyright errors, 0 ruff errors, format leaves files unchanged or applies trivial fixes.

- [ ] **Step 8.4: Commit any formatter fixes**

```bash
git add -A
git commit -m "rotate_profile: cycle-equivalence test + lint/format" || echo "nothing to commit"
```

---

## Task 9: Filename derivation helper

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Test: `tests/test_rotate_profile.py`

Filename derivation reuses `profile_cli._safe_file_stem` (which preserves `&`, unlike `profile_store._slugify`). The output filename is `<stem>_v0.1.json`.

- [ ] **Step 9.1: Add test**

Append to `tests/test_rotate_profile.py`:

```python
from pathlib import Path

from bridge_engine.rotate_profile import _derived_output_path


def test_derived_output_path(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    out = _derived_output_path("We Open 1NT and Opps Overcall", profiles_dir)
    assert out == profiles_dir / "We_Open_1NT_and_Opps_Overcall_v0.1.json"


def test_derived_output_path_preserves_ampersand(tmp_path):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    out = _derived_output_path("We Open & Opps TO Dbl", profiles_dir)
    assert out.name == "We_Open_&_Opps_TO_Dbl_v0.1.json"
```

- [ ] **Step 9.2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_rotate_profile.py::test_derived_output_path -v`

Expected: ImportError on `_derived_output_path`.

- [ ] **Step 9.3: Implement helper**

Add to `bridge_engine/rotate_profile.py` (alongside the imports section):

```python
from pathlib import Path

from bridge_engine.profile_cli import _safe_file_stem
```

Then add a helper:

```python
def _derived_output_path(profile_name: str, profiles_dir: Path) -> Path:
    """Filename = '<safe_stem>_v0.1.json' inside profiles_dir."""
    stem = _safe_file_stem(profile_name)
    return profiles_dir / f"{stem}_v0.1.json"
```

- [ ] **Step 9.4: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile.py -v`

Expected: all 28 tests pass.

- [ ] **Step 9.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile.py
git commit -m "rotate_profile: _derived_output_path helper"
```

---

## Task 10: CLI `main()` — happy path + name override

**Files:**
- Modify: `bridge_engine/rotate_profile.py`
- Create: `tests/test_rotate_profile_cli.py`

The CLI:
- Loads input JSON
- Calls `rotate_profile()`
- Sets `rotated_from` to the source filename (basename only)
- Validates via `HandProfile.from_dict` + `validate_profile`
- Writes via `profile_store._atomic_write` to the derived path inside `profile_store._profiles_dir(base_dir)` (or `--output`)
- Returns 0 on success; the outer `if __name__ == "__main__"` calls `sys.exit(main())`.

- [ ] **Step 10.1: Add CLI happy-path test**

Create `tests/test_rotate_profile_cli.py`:

```python
"""CLI tests for bridge_engine.rotate_profile.main()."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_profile_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_cli_success_exit_0_writes_file(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    src_path = profiles_dir / "Opps_Open_1NT_and_we_Overcall_v1.0.json"
    _write_profile_json(src_path, make_profile_dict())

    rc = main([str(src_path)])
    assert rc == 0

    out_path = profiles_dir / "We_Open_1NT_and_Opps_Overcall_v0.1.json"
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["dealer"] == "N"
    assert written["profile_name"] == "We Open 1NT and Opps Overcall"
    assert written["version"] == "0.1"
    assert written["rotated_from"] == src_path.name


def test_cli_name_override(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    src_path = profiles_dir / "Opps_Open_1NT_and_we_Overcall_v1.0.json"
    _write_profile_json(src_path, make_profile_dict())

    rc = main([str(src_path), "--name", "My Custom Profile"])
    assert rc == 0

    out_path = profiles_dir / "My_Custom_Profile_v0.1.json"
    assert out_path.exists()
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["profile_name"] == "My Custom Profile"
```

- [ ] **Step 10.2: Run to confirm failure**

Run: `.venv/bin/pytest tests/test_rotate_profile_cli.py -v`

Expected: ImportError on `main`.

- [ ] **Step 10.3: Implement `main()`**

Append to `bridge_engine/rotate_profile.py`. Note: `ProfileError` was imported in Task 7 (Step 7.3); do NOT re-import it here. `Path` was imported in Task 9 (Step 9.3); do NOT re-import.

```python
import argparse
import json
import sys

from bridge_engine import profile_store
from bridge_engine.hand_profile_model import HandProfile
from bridge_engine.hand_profile_validate import validate_profile


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m bridge_engine.rotate_profile",
        description="Rotate a hand profile around the table (W→N→E→S→W).",
    )
    p.add_argument("input", help="Path to the source profile JSON file.")
    p.add_argument("--name", dest="new_name", default=None,
                   help="Override the rotated profile_name (bypasses the pronoun swap).")
    p.add_argument("--description", dest="new_description", default=None,
                   help="Override the rotated description.")
    p.add_argument("--output", dest="output", default=None,
                   help="Override the derived output path.")
    p.add_argument("--force", action="store_true",
                   help="Overwrite the output file if it already exists.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_argparser().parse_args(argv)

    src_path = Path(args.input)
    try:
        with src_path.open("r", encoding="utf-8") as f:
            src_dict = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print(f"Cannot read input: {e}", file=sys.stderr)
        return 1

    try:
        rotated = rotate_profile(
            src_dict, new_name=args.new_name, new_description=args.new_description
        )
    except ProfileError as e:
        print(str(e), file=sys.stderr)
        return 2

    rotated["rotated_from"] = src_path.name

    try:
        profile = HandProfile.from_dict(rotated)
        validate_profile(profile)
    except (ProfileError, KeyError, TypeError, ValueError) as e:
        print(f"Rotation produced invalid profile: {e}", file=sys.stderr)
        return 2

    profiles_dir = profile_store._profiles_dir()
    out_path = (
        Path(args.output) if args.output is not None
        else _derived_output_path(rotated["profile_name"], profiles_dir)
    )
    if out_path.exists() and not args.force:
        print(f"Output exists: {out_path}. Pass --force to overwrite.", file=sys.stderr)
        return 4

    profile_store._atomic_write(
        out_path, json.dumps(rotated, indent=2, sort_keys=True) + "\n"
    )

    src = src_dict.get("dealer", "?")
    print(
        f"Rotated: dealer {src} → {rotated.get('dealer', '?')}, "
        f"NS↔EW linked profiles swapped, "
        f"{len(rotated.get('seat_profiles', {}))} seat profiles rekeyed. "
        f"Wrote {out_path}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 10.4: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile_cli.py -v`

Expected: 2 passed.

- [ ] **Step 10.5: Commit**

```bash
git add bridge_engine/rotate_profile.py tests/test_rotate_profile_cli.py
git commit -m "rotate_profile: CLI main() with happy path + name override"
```

---

## Task 11: CLI exit codes for error paths

**Files:**
- Modify: `tests/test_rotate_profile_cli.py`
- (No code change to `rotate_profile.py` — `main()` already handles all branches.)

- [ ] **Step 11.1: Add error-path tests**

Append to `tests/test_rotate_profile_cli.py`:

```python
def test_cli_input_not_found_exit_1(tmp_path, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    rc = main([str(tmp_path / "nonexistent.json")])
    assert rc == 1


def test_cli_bad_json_exit_1(tmp_path, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    rc = main([str(bad)])
    assert rc == 1


def test_cli_already_rotated_exit_2(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    src = make_profile_dict()
    src["rotated_from"] = "earlier.json"
    src_path = profiles_dir / "X_v1.0.json"
    _write_profile_json(src_path, src)
    rc = main([str(src_path)])
    assert rc == 2


def test_cli_bad_name_pattern_exit_2(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    src = make_profile_dict()
    src["profile_name"] = "Big Hands"
    src_path = profiles_dir / "Big_Hands_v0.1.json"
    _write_profile_json(src_path, src)
    rc = main([str(src_path)])
    assert rc == 2


def test_cli_validation_failure_exit_2(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    src = make_profile_dict()
    # Break the linked profile so validate_profile() fails: out-of-bounds primary
    # subprofile index in the map. (Each seat in the fixture has exactly 1
    # subprofile, so primary index 99 is invalid.)
    src["ns_linked_profile"]["subprofile_map"] = {"99": [1]}
    src_path = profiles_dir / "Opps_Open_1NT_and_we_Overcall_v1.0.json"
    _write_profile_json(src_path, src)
    rc = main([str(src_path)])
    assert rc == 2


def test_cli_output_exists_exit_4(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    src_path = profiles_dir / "Opps_Open_1NT_and_we_Overcall_v1.0.json"
    _write_profile_json(src_path, make_profile_dict())
    out_path = profiles_dir / "We_Open_1NT_and_Opps_Overcall_v0.1.json"
    out_path.write_text("{}", encoding="utf-8")
    rc = main([str(src_path)])
    assert rc == 4


def test_cli_force_overwrites(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    src_path = profiles_dir / "Opps_Open_1NT_and_we_Overcall_v1.0.json"
    _write_profile_json(src_path, make_profile_dict())
    out_path = profiles_dir / "We_Open_1NT_and_Opps_Overcall_v0.1.json"
    out_path.write_text("{}", encoding="utf-8")
    rc = main([str(src_path), "--force"])
    assert rc == 0
    written = json.loads(out_path.read_text(encoding="utf-8"))
    assert written["dealer"] == "N"
```

- [ ] **Step 11.2: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile_cli.py -v`

Expected: 9 passed (2 from Task 10 + 7 new).

If `test_cli_validation_failure_exit_2` doesn't actually fail validation, the chosen breakage isn't strict enough. Fallback known-invalidators: `src["dealer"] = "Z"` (rejected by `HandProfile.from_dict`) or set `ns_linked_profile.primary_seat = "Z"`. The test must verify the error path, not coincidentally succeed.

- [ ] **Step 11.3: Commit**

```bash
git add tests/test_rotate_profile_cli.py
git commit -m "rotate_profile: CLI exit-code coverage (1, 2, 4)"
```

---

## Task 12: Integration tests with real profiles

**Files:**
- Create: `tests/test_rotate_profile_integration.py`

These tests read the actual `profiles/*.json` files from the repo. Output goes to `tmp_path` so the working tree stays clean.

- [ ] **Step 12.1: Add integration tests**

Create `tests/test_rotate_profile_integration.py`:

```python
"""Integration tests: rotate real profile files from profiles/."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bridge_engine.hand_profile_model import HandProfile
from bridge_engine.hand_profile_validate import validate_profile
from bridge_engine.rotate_profile import rotate_profile


REAL_TARGET_PROFILES = [
    "Opps_Open_3_Weak_2s_and_we_Compete_v1.0.json",
    "Opps_Open_Strong_1NT_and_we_Overcall_Cappeletti_v1.0.json",
    "Opps_Open_&_Our_TO_Dbl_v0.9.json",
    "Opps_Open_&_Our_TO_Dbl_Balancing_v0.9.json",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("filename", REAL_TARGET_PROFILES)
def test_rotate_each_real_profile(filename, tmp_path):
    src_path = _project_root() / "profiles" / filename
    if not src_path.exists():
        pytest.skip(f"{filename} not present in profiles/")

    src_dict = json.loads(src_path.read_text(encoding="utf-8"))
    rotated = rotate_profile(src_dict)
    rotated["rotated_from"] = src_path.name

    profile = HandProfile.from_dict(rotated)
    validate_profile(profile)

    # Sanity: dealer rotated, version reset, name swapped.
    assert rotated["dealer"] != src_dict["dealer"]
    assert rotated["version"] == "0.1"
    assert "Opps" not in rotated["profile_name"] or "We" in rotated["profile_name"]
```

- [ ] **Step 12.2: Run tests**

Run: `.venv/bin/pytest tests/test_rotate_profile_integration.py -v`

Expected: 4 passed (one per real profile). If any are skipped, the file isn't present — investigate before continuing.

- [ ] **Step 12.3: Commit**

```bash
git add tests/test_rotate_profile_integration.py
git commit -m "rotate_profile: integration tests over the 4 real target profiles"
```

---

## Task 13: Admin menu entry

**Files:**
- Modify: `bridge_engine/rotate_profile.py` (add `run_rotation_menu`)
- Modify: `bridge_engine/orchestrator.py` (add menu entry)

The menu entry should:
1. List existing profiles in `profiles/` (reuse `profile_cli._load_profiles()`).
2. Let the user pick one.
3. Optionally prompt for a name override.
4. Run the same rotation pipeline as `main()` and report the outcome.

For brevity, the function calls `main(argv)` with constructed argv, so the same code path handles both surfaces.

- [ ] **Step 13.1: Add `run_rotation_menu`**

Append to `bridge_engine/rotate_profile.py`:

```python
def run_rotation_menu() -> None:
    """Interactive entry for Admin → 'Rotate a profile'."""
    from bridge_engine import profile_cli

    profiles = profile_cli._load_profiles()
    if not profiles:
        print("No profiles available to rotate.")
        return

    print("Choose a profile to rotate:")
    for i, (path, profile) in enumerate(profiles, start=1):
        print(f"  {i}) {profile.profile_name} ({path.name})")
    print("  0) Cancel")

    raw = input("Selection: ").strip()
    try:
        idx = int(raw)
    except ValueError:
        print("Invalid selection.")
        return
    if idx == 0:
        return
    if not (1 <= idx <= len(profiles)):
        print("Invalid selection.")
        return

    src_path, _ = profiles[idx - 1]

    new_name = input("New name (blank = auto pronoun-swap): ").strip() or None

    argv: list[str] = [str(src_path)]
    if new_name is not None:
        argv += ["--name", new_name]

    rc = main(argv)
    if rc != 0:
        print(f"(rotation failed with exit code {rc})")
```

- [ ] **Step 13.2: Wire into the Admin menu**

Read `bridge_engine/orchestrator.py` to confirm the current Admin menu shape:

```bash
sed -n '410,425p' bridge_engine/orchestrator.py
```

Expected (verified against current code at the time of writing):

```python
def admin_menu() -> None:
    """Admin / tools submenu (LIN combiner, draft tools, diagnostics, etc.)."""
    _run_menu_loop(
        title="Bridge Hand Generator – Admin",
        items=[
            ("Exit", None),
            ("LIN Combiner", lin_tools.run_lin_combiner),
            ("Recover/Delete *_TEST.json drafts", profile_cli.run_draft_tools),
            ("Profile Diagnostic", _run_profile_diagnostic_interactive),
            ("Help", _help_admin),
        ],
        help_key="admin_menu",
    )
```

Add a new entry. Use the Edit tool to insert `("Rotate a profile", rotate_profile.run_rotation_menu),` immediately after the LIN Combiner line. (Result: it sits between LIN Combiner and the Recover/Delete drafts entry.)

Also add at the top of `orchestrator.py` (alongside the other `from . import` lines):

```python
from . import rotate_profile
```

- [ ] **Step 13.3: Verify the menu loads (smoke check)**

Run: `.venv/bin/python -c "from bridge_engine.orchestrator import admin_menu; print('ok')"`

Expected: `ok`. If ImportError, check the import line you added.

- [ ] **Step 13.4: Run the full test suite**

Run: `.venv/bin/pytest -q`

Expected: all tests pass (the existing 578 + ~37 new = ~615). Investigate any regressions before continuing.

- [ ] **Step 13.5: Run pyright + ruff on everything modified**

Run:

```bash
npx pyright bridge_engine/
.venv/bin/ruff check bridge_engine/ tests/
.venv/bin/ruff format bridge_engine/ tests/
```

Expected: 0 pyright errors, 0 ruff errors. Format may rewrite a few files — that's fine.

- [ ] **Step 13.6: Commit**

```bash
git add bridge_engine/rotate_profile.py bridge_engine/orchestrator.py
git commit -m "rotate_profile: Admin menu entry + run_rotation_menu()"
```

---

## Task 14: Manual verification (post-merge sanity)

This is a checklist, not code. Run each step and confirm expected output.

- [ ] **Step 14.1: Rotate the first target profile via CLI**

Run: `.venv/bin/python -m bridge_engine.rotate_profile profiles/Opps_Open_3_Weak_2s_and_we_Compete_v1.0.json`

Expected stdout: `Rotated: dealer ... → ..., NS↔EW linked profiles swapped, 4 seat profiles rekeyed. Wrote .../profiles/We_Open_3_Weak_2s_and_Opps_Compete_v0.1.json.`

- [ ] **Step 14.2: Rotate the remaining three** (one at a time)

```bash
.venv/bin/python -m bridge_engine.rotate_profile profiles/Opps_Open_Strong_1NT_and_we_Overcall_Cappeletti_v1.0.json
.venv/bin/python -m bridge_engine.rotate_profile 'profiles/Opps_Open_&_Our_TO_Dbl_v0.9.json'
.venv/bin/python -m bridge_engine.rotate_profile 'profiles/Opps_Open_&_Our_TO_Dbl_Balancing_v0.9.json'
```

Expected: 3 success messages. Confirm the 4 new files exist:

```bash
ls profiles/We_Open_*.json profiles/'We_Open_&_'*.json
```

- [ ] **Step 14.3: Launch the app, verify the rotated profiles appear and generate**

Run: `.venv/bin/python -m bridge_engine`

Navigate: Profile management → list profiles → pick a "We Open ..." entry → Deal generation → produce a few deals → eyeball the seat assignments and HCP/shape distributions.

- [ ] **Step 14.4: Verify the Admin menu entry works**

In the same app run: Admin → "Rotate a profile" → pick any profile → confirm a new file is produced.

- [ ] **Step 14.5: Final commit if anything was tweaked during manual verification**

```bash
git status
# If anything changed during manual verification, commit it.
```

---

## Self-review checklist

Run after the plan is complete, before handing off.

**Spec coverage:**
- ✅ Pure `rotate_profile()` function — Tasks 1, 3–8
- ✅ All rotation rules (`dealer`, `hand_dealing_order`, `seat_profiles`, contingents, exclusions, linked profiles) — Tasks 3–6
- ✅ `tag`, `description`, unchanged fields preserved — Task 3
- ✅ `version` reset, `rotated_from` set — Tasks 3, 10
- ✅ Legacy fields stripped — Task 3
- ✅ Pronoun swap algorithm — Task 7
- ✅ Already-rotated guard — Task 7
- ✅ No-pronouns guard — Task 7
- ✅ Filename derivation — Task 9
- ✅ CLI happy path + overrides — Task 10
- ✅ All exit codes (0, 1, 2, 4) — Tasks 10, 11
- ✅ Admin menu entry — Task 13
- ✅ Integration tests over 4 real profiles — Task 12
- ✅ Manual verification — Task 14

**Placeholders:** none — every step contains the actual code or command.

**Type consistency:** function names match across tasks (`rotate_profile`, `_rotate_seat`, `_rotate_subprofile_contingents`, `_swap_and_rotate_linked`, `_swap_pronouns`, `_derived_output_path`, `main`, `run_rotation_menu`).

**Note:** Exit code 3 was reserved in the spec for smoke-test failure but is unused (smoke test was dropped during review). The error-policy table in the spec already documents this. No task needed.
