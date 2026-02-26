from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

# Type alias used in annotations throughout this file.
Seat = str


class ProfileError(Exception):
    """Raised when a hand profile or its constraints are invalid."""


# ---------------------------------------------------------------------------
# Low-level constraint building blocks
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubprofileExclusionClause:
    """A single clause in a subprofile exclusion rule."""

    group: str  # "ANY", "MAJOR", "MINOR"
    length_eq: int
    count: int

    def to_dict(self) -> Dict[str, Any]:
        return {"group": self.group, "length_eq": self.length_eq, "count": self.count}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubprofileExclusionClause":
        return cls(
            group=str(data["group"]),
            length_eq=int(data["length_eq"]),
            count=int(data["count"]),
        )


@dataclass
class SubprofileExclusionData:
    seat: str  # "N", "E", "S", "W"
    subprofile_index: int  # 1-based
    excluded_shapes: Optional[List[str]] = None
    clauses: Optional[List[SubprofileExclusionClause]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "seat": self.seat,
            "subprofile_index": self.subprofile_index,
        }
        if self.excluded_shapes is not None:
            d["excluded_shapes"] = list(self.excluded_shapes)
        if self.clauses is not None:
            d["clauses"] = [c.to_dict() for c in self.clauses]
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubprofileExclusionData":
        clauses_raw = data.get("clauses")
        clauses = [SubprofileExclusionClause.from_dict(c) for c in clauses_raw] if clauses_raw is not None else None
        return cls(
            seat=str(data["seat"]),
            subprofile_index=int(data["subprofile_index"]),
            excluded_shapes=data.get("excluded_shapes"),
            clauses=clauses,
        )

    def validate(self, profile: "HandProfile") -> None:
        if self.seat not in ("N", "E", "S", "W"):
            raise ProfileError(f"Invalid seat in exclusion: {self.seat}")

        seat_profile = profile.seat_profiles.get(self.seat)
        if seat_profile is None:
            raise ProfileError(f"Seat {self.seat} not present in profile")

        if not (1 <= self.subprofile_index <= len(seat_profile.subprofiles)):
            raise ProfileError(f"Invalid subprofile index {self.subprofile_index} for seat {self.seat}")

        if self.excluded_shapes and self.clauses:
            raise ProfileError("Exclusion may specify either excluded_shapes or clauses, not both")

        if not self.excluded_shapes and not self.clauses:
            raise ProfileError("Exclusion must specify excluded_shapes or clauses")

        if self.excluded_shapes:
            seen: Set[str] = set()
            for s in self.excluded_shapes:
                if s in seen:
                    raise ProfileError(f"Duplicate excluded shape: {s}")
                seen.add(s)

                if not (isinstance(s, str) and len(s) == 4 and all(c in "0123456789x" for c in s)):
                    raise ProfileError(f"Invalid shape: {s}")
                # For fully specified shapes (no wildcards), enforce sum == 13.
                # For wildcard shapes, just check that specified digits don't exceed 13.
                specified_digits = [int(c) for c in s if c != "x"]
                if "x" not in s:
                    if sum(specified_digits) != 13:
                        raise ProfileError(f"Shape does not sum to 13: {s}")
                else:
                    if sum(specified_digits) > 13:
                        raise ProfileError(f"Specified digits exceed 13: {s}")

        if self.clauses:
            if not (1 <= len(self.clauses) <= 2):
                raise ProfileError("Exclusion may have at most 2 clauses")

            for c in self.clauses:
                if c.group not in ("ANY", "MAJOR", "MINOR"):
                    raise ProfileError(f"Invalid group: {c.group}")
                if not (0 <= c.length_eq <= 13):
                    raise ProfileError(f"Invalid length_eq: {c.length_eq}")

                max_count = 4 if c.group == "ANY" else 2
                if not (0 <= c.count <= max_count):
                    raise ProfileError(f"Invalid count {c.count} for group {c.group}")


@dataclass(frozen=True)
class SuitRange:
    """
    Range constraints for a single suit.

    Defaults represent a fully open range.
    """

    min_cards: int = 0
    max_cards: int = 13
    min_hcp: int = 0
    max_hcp: int = 37

    def __post_init__(self) -> None:
        if not (0 <= self.min_cards <= 13 and 0 <= self.max_cards <= 13):
            raise ProfileError(f"SuitRange card bounds must be within 0–13, got {self.min_cards}–{self.max_cards}.")
        if self.min_cards > self.max_cards:
            raise ProfileError(f"SuitRange min_cards cannot exceed max_cards ({self.min_cards}>{self.max_cards}).")
        if not (0 <= self.min_hcp <= 37 and 0 <= self.max_hcp <= 37):
            raise ProfileError(f"SuitRange HCP bounds must be within 0–37, got {self.min_hcp}–{self.max_hcp}.")
        if self.min_hcp > self.max_hcp:
            raise ProfileError(f"SuitRange min_hcp cannot exceed max_hcp ({self.min_hcp}>{self.max_hcp}).")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_cards": self.min_cards,
            "max_cards": self.max_cards,
            "min_hcp": self.min_hcp,
            "max_hcp": self.max_hcp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SuitRange:
        return cls(
            min_cards=int(data.get("min_cards", 0)),
            max_cards=int(data.get("max_cards", 13)),
            min_hcp=int(data.get("min_hcp", 0)),
            max_hcp=int(data.get("max_hcp", 37)),
        )


@dataclass(frozen=True)
class StandardSuitConstraints:
    """
    Standard constraints applied to an entire hand.

    Attributes
    ----------
    spades, hearts, diamonds, clubs
        Per-suit ranges.
    total_min_hcp, total_max_hcp
        Total HCP range for the hand.
    """

    spades: SuitRange
    hearts: SuitRange
    diamonds: SuitRange
    clubs: SuitRange
    total_min_hcp: int = 0
    total_max_hcp: int = 37

    def __post_init__(self) -> None:
        if not (0 <= self.total_min_hcp <= 37 and 0 <= self.total_max_hcp <= 37):
            raise ProfileError(
                f"total_min_hcp / total_max_hcp must be within 0–37 (got {self.total_min_hcp}–{self.total_max_hcp})."
            )
        if self.total_min_hcp > self.total_max_hcp:
            raise ProfileError(
                f"total_min_hcp cannot exceed total_max_hcp ({self.total_min_hcp}>{self.total_max_hcp})."
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spades": self.spades.to_dict(),
            "hearts": self.hearts.to_dict(),
            "diamonds": self.diamonds.to_dict(),
            "clubs": self.clubs.to_dict(),
            "total_min_hcp": self.total_min_hcp,
            "total_max_hcp": self.total_max_hcp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StandardSuitConstraints:
        return cls(
            spades=SuitRange.from_dict(data["spades"]),
            hearts=SuitRange.from_dict(data["hearts"]),
            diamonds=SuitRange.from_dict(data["diamonds"]),
            clubs=SuitRange.from_dict(data["clubs"]),
            total_min_hcp=int(data.get("total_min_hcp", 0)),
            total_max_hcp=int(data.get("total_max_hcp", 37)),
        )


# ---------------------------------------------------------------------------
# Random Suit & Partner Contingent
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SuitPairOverride:
    """
    Optional override when required_suits_count == 2 and a specific
    unordered pair of suits should use special SuitRanges.

    Example:
      If the two suits are (D, C), use:
        - first_range for Diamonds
        - second_range for Clubs
    """

    suits: List[str]  # exactly 2 suits like ["D", "C"]
    first_range: SuitRange
    second_range: SuitRange

    def __post_init__(self) -> None:
        if len(self.suits) != 2:
            raise ProfileError(f"SuitPairOverride.suits must contain exactly 2 suits, got {len(self.suits)}.")
        for s in self.suits:
            if s not in ("S", "H", "D", "C"):
                raise ProfileError(f"Invalid suit in pair override: {s}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "suits": list(self.suits),
            "first_range": self.first_range.to_dict(),
            "second_range": self.second_range.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SuitPairOverride:
        return cls(
            suits=list(data["suits"]),
            first_range=SuitRange.from_dict(data["first_range"]),
            second_range=SuitRange.from_dict(data["second_range"]),
        )


@dataclass(frozen=True)
class RandomSuitConstraintData:
    """
    Random Suit constraint:

      • required_suits_count:
          how many suits (from allowed_suits) must satisfy the ranges.
      • allowed_suits:
          which suits are eligible for random selection.
      • suit_ranges:
          per-suit ranges used in the base case.
      • pair_overrides:
          when required_suits_count == 2, optional overrides for
          specific unordered suit pairs.

    The generator will:
      • randomly choose required_suits_count distinct suits from allowed_suits.
      • map each chosen suit to a SuitRange.
        – either from suit_ranges (default),
        – or from a matching SuitPairOverride (if count==2).
      • require every chosen suit to satisfy its SuitRange.
    """

    required_suits_count: int
    allowed_suits: List[str]
    suit_ranges: List[SuitRange]
    pair_overrides: List[SuitPairOverride] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.required_suits_count <= 0:
            raise ProfileError(f"required_suits_count must be positive, got {self.required_suits_count}.")
        if not self.allowed_suits:
            raise ProfileError("allowed_suits must not be empty.")
        allowed_set = set(self.allowed_suits)
        if not allowed_set.issubset({"S", "H", "D", "C"}):
            raise ProfileError(f"allowed_suits must be subset of {{S,H,D,C}}, got {self.allowed_suits}.")
        if self.required_suits_count > len(allowed_set):
            raise ProfileError(
                "required_suits_count cannot exceed number of distinct allowed_suits "
                f"({self.required_suits_count}>{len(allowed_set)})."
            )
        if len(self.suit_ranges) < self.required_suits_count:
            raise ProfileError("suit_ranges must contain at least required_suits_count entries.")
        if self.required_suits_count != 2 and self.pair_overrides:
            raise ProfileError("pair_overrides must be empty unless required_suits_count == 2.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "required_suits_count": self.required_suits_count,
            "allowed_suits": list(self.allowed_suits),
            "suit_ranges": [sr.to_dict() for sr in self.suit_ranges],
            "pair_overrides": [po.to_dict() for po in self.pair_overrides],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RandomSuitConstraintData:
        return cls(
            required_suits_count=int(data["required_suits_count"]),
            allowed_suits=list(data["allowed_suits"]),
            suit_ranges=[SuitRange.from_dict(d) for d in data["suit_ranges"]],
            pair_overrides=[SuitPairOverride.from_dict(d) for d in data.get("pair_overrides", [])],
        )


@dataclass(frozen=True)
class PartnerContingentData:
    """
    Partner Contingent constraint:

      • partner_seat:
          which seat (N/E/S/W) has the Random Suit constraint.
      • suit_range:
          single SuitRange to be satisfied on at least one of the suits
          chosen by partner's Random Suit constraint.
      • use_non_chosen_suit:
          if True, target the suit partner did NOT choose (inverse).
          Requires partner RS to have exactly 1 non-chosen suit
          (allowed_suits - required_suits_count == 1).

    Semantics implemented in Section C:
      • Let partner_suits = suits chosen by partner's RandomSuitConstraintData.
      • If use_non_chosen_suit is False (default):
          This hand must have at least one suit in partner_suits that satisfies suit_range.
      • If use_non_chosen_suit is True:
          Compute non_chosen = allowed_suits - partner_suits; target non_chosen[0].
    """

    partner_seat: str  # 'N', 'E', 'S', or 'W'
    suit_range: SuitRange
    use_non_chosen_suit: bool = False  # target inverse of partner's RS choice

    def __post_init__(self) -> None:
        if self.partner_seat not in ("N", "E", "S", "W"):
            raise ProfileError(f"Invalid partner_seat: {self.partner_seat}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partner_seat": self.partner_seat,
            "suit_range": self.suit_range.to_dict(),
            "use_non_chosen_suit": self.use_non_chosen_suit,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PartnerContingentData:
        return cls(
            partner_seat=str(data["partner_seat"]),
            suit_range=SuitRange.from_dict(data["suit_range"]),
            use_non_chosen_suit=data.get("use_non_chosen_suit", False),
        )


@dataclass(frozen=True)
class OpponentContingentSuitData:
    """
    Opponent Contingent-Suit constraint.

    opponent_seat:
        Which seat (N/E/S/W) has the Random Suit constraint.
    suit_range:
        SuitRange to be satisfied in that opponent's Contingent Suit
        (the single canonical suit derived from their Random Suit
        constraint).
    use_non_chosen_suit:
        When True, target the suit the opponent did NOT choose instead
        of the suit they chose. E.g., if opponent RS picks H from [S, H],
        OC targets S (the non-chosen suit).
    """

    opponent_seat: str  # 'N', 'E', 'S', or 'W'
    suit_range: SuitRange
    # When True, target the suit the opponent did NOT choose (the inverse).
    # E.g., if opponent RS picks H from [S, H], OC targets S instead of H.
    use_non_chosen_suit: bool = False

    def __post_init__(self) -> None:
        if self.opponent_seat not in ("N", "E", "S", "W"):
            raise ProfileError(f"Invalid opponent_seat: {self.opponent_seat}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opponent_seat": self.opponent_seat,
            "suit_range": self.suit_range.to_dict(),
            "use_non_chosen_suit": self.use_non_chosen_suit,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpponentContingentSuitData":
        return cls(
            opponent_seat=str(data["opponent_seat"]),
            suit_range=SuitRange.from_dict(data["suit_range"]),
            use_non_chosen_suit=bool(data.get("use_non_chosen_suit", False)),
        )


# ---------------------------------------------------------------------------
# SubProfile & SeatProfile
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubProfile:
    """
    A single sub-profile for one seat.

    At most one of
      - random_suit_constraint
      - partner_contingent_constraint
      - opponents_contingent_suit_constraint
    may be present, or none (Standard-only).

    Phase 3: ns_role_usage controls how this subprofile is used when NS
    driver/follower semantics are enabled on the HandProfile. For E/W seats
    this should effectively remain "any".
    """

    standard: StandardSuitConstraints

    # Optional human-readable label for this sub-profile (e.g., "Strong opener").
    # Purely cosmetic — not used by deal generation or constraint matching.
    name: Optional[str] = None

    random_suit_constraint: Optional[RandomSuitConstraintData] = None
    partner_contingent_constraint: Optional[PartnerContingentData] = None
    opponents_contingent_suit_constraint: Optional[OpponentContingentSuitData] = None
    weight_percent: float = 0.0

    # Phase 3: NS role classification for this subprofile (for N/S seats).
    #
    # Allowed values:
    #   - "any"           – usable whether the seat is NS driver or follower
    #   - "driver_only"   – only usable when this seat is the NS driver
    #   - "follower_only" – only usable when this seat is the NS follower
    #
    # For legacy profiles and for EW seats, this defaults to "any".
    ns_role_usage: str = "any"

    # EW role classification (parallel to ns_role_usage, for E/W seats).
    #
    # Allowed values:
    #   - "any"           – usable whether the seat is EW driver or follower
    #   - "driver_only"   – only usable when this seat is the EW driver
    #   - "follower_only" – only usable when this seat is the EW follower
    #
    # For legacy profiles and for NS seats, this defaults to "any".
    ew_role_usage: str = "any"

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "standard": self.standard.to_dict(),
            "random_suit_constraint": (
                self.random_suit_constraint.to_dict() if self.random_suit_constraint is not None else None
            ),
            "partner_contingent_constraint": (
                self.partner_contingent_constraint.to_dict() if self.partner_contingent_constraint is not None else None
            ),
            "opponents_contingent_suit_constraint": (
                self.opponents_contingent_suit_constraint.to_dict()
                if self.opponents_contingent_suit_constraint is not None
                else None
            ),
            "weight_percent": self.weight_percent,
            # JSON field names for NS/EW role metadata.
            "ns_role_usage": self.ns_role_usage,
            "ew_role_usage": self.ew_role_usage,
        }
        # Only include name when set (keeps JSON clean for unnamed sub-profiles).
        if self.name is not None:
            d["name"] = self.name
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubProfile":
        """
        Backwards compatible loader for SubProfile, including Phase 3 metadata.

        Supports both:
          - new-style "ns_role_usage" (preferred)
          - earlier experimental "ns_role_for_seat" (mapped to usage)
        """
        # Optional name (strip whitespace; treat empty/blank as None).
        raw_name = data.get("name")
        name: Optional[str] = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else None

        rsc_data = data.get("random_suit_constraint")
        pc_data = data.get("partner_contingent_constraint")
        oc_data = data.get("opponents_contingent_suit_constraint")

        # Resolve NS role usage with legacy key support.
        if "ns_role_usage" in data:
            ns_role_usage = str(data["ns_role_usage"])
        elif "ns_role_for_seat" in data:
            legacy_role = str(data["ns_role_for_seat"]).lower()
            if legacy_role == "driver":
                ns_role_usage = "driver_only"
            elif legacy_role == "follower":
                ns_role_usage = "follower_only"
            else:
                # "neutral" or anything else → "any"
                ns_role_usage = "any"
        else:
            ns_role_usage = "any"

        # EW role usage (no legacy key support needed — new field).
        ew_role_usage = str(data.get("ew_role_usage", "any"))

        return cls(
            standard=StandardSuitConstraints.from_dict(data["standard"]),
            name=name,
            random_suit_constraint=(RandomSuitConstraintData.from_dict(rsc_data) if rsc_data is not None else None),
            partner_contingent_constraint=(PartnerContingentData.from_dict(pc_data) if pc_data is not None else None),
            opponents_contingent_suit_constraint=(
                OpponentContingentSuitData.from_dict(oc_data) if oc_data is not None else None
            ),
            weight_percent=float(data.get("weight_percent", 0.0)),
            ns_role_usage=ns_role_usage,
            ew_role_usage=ew_role_usage,
        )


def sub_label(idx: int, sub: Any) -> str:
    """Format a display label for a sub-profile: 'Sub-profile {idx}' or 'Sub-profile {idx} (name)'.

    Accepts any object with an optional `name` attribute (SubProfile, SimpleNamespace, etc.)
    so callers using test stubs or synthetic objects don't crash.
    """
    name = getattr(sub, "name", None)
    if name:
        return f"Sub-profile {idx} ({name})"
    return f"Sub-profile {idx}"


@dataclass(frozen=True)
class SeatProfile:
    """
    All constraints for a single seat (N/E/S/W).

    Attributes
    ----------
    seat
        One of "N", "E", "S", "W".
    subprofiles
        List of possible sub-profiles for this seat. At deal time, Section C
        randomly chooses one sub-profile per seat per deal, and holds it
        fixed for that deal.
    """

    seat: str
    subprofiles: List[SubProfile]

    def __post_init__(self) -> None:
        if self.seat not in ("N", "E", "S", "W"):
            raise ProfileError(f"Invalid seat in SeatProfile: {self.seat}")
        if not self.subprofiles:
            raise ProfileError(f"SeatProfile for seat {self.seat} must have at least one SubProfile.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seat": self.seat,
            "subprofiles": [sp.to_dict() for sp in self.subprofiles],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SeatProfile:
        return cls(
            seat=str(data["seat"]),
            subprofiles=[SubProfile.from_dict(d) for d in data["subprofiles"]],
        )


# -----------------------------------------------------------------------
# HandProfile (whole profile)
# -----------------------------------------------------------------------


def _default_dealing_order(dealer: str) -> List[str]:
    """
    Return default dealing order: dealer + clockwise rotation.

    Examples:
        dealer="N" → ["N", "E", "S", "W"]
        dealer="E" → ["E", "S", "W", "N"]
        dealer="S" → ["S", "W", "N", "E"]
        dealer="W" → ["W", "N", "E", "S"]
    """
    seats = ["N", "E", "S", "W"]
    idx = seats.index(dealer)
    return seats[idx:] + seats[:idx]


@dataclass
class HandProfile:
    """
    Complete profile definition for Section B.

    Attributes
    ----------
    profile_name
        Name used for persistence and logs.
    description
        Human-readable explanation.
    dealer
        'N', 'E', 'S', or 'W'.
    hand_dealing_order
        A permutation of ["N", "E", "S", "W"]. Stored as a display hint;
        actual dealing order is auto-computed at runtime by the v2 builder
        (`_compute_dealing_order`).
    tag
        "Opener" or "Overcaller".
    seat_profiles
        Mapping from seat ("N", "E", "S", "W") to SeatProfile.
    author
        Free text author (optional, default empty).
    version
        Free text version string (e.g. "0.2", optional, default empty).

    Full hand profile for one scenario.

    NOTE: ns_role_mode controls who “drives” the N-S partnership at
    runtime.  When set to a driver mode (north_drives, south_drives,
    random_driver), the deal generator uses role filtering to restrict
    subprofile selection based on ns_role_usage.  When combined with
    ns_bespoke_map, it also enables bespoke subprofile matching.
    The default “no_driver_no_index” disables both features.
    """

    profile_name: str
    description: str
    dealer: str
    hand_dealing_order: List[str]
    tag: str
    seat_profiles: Dict[str, SeatProfile]
    author: str = ""
    version: str = ""
    rotate_deals_by_default: bool = True
    # "no_driver_no_index" (default), "north_drives", "south_drives", or "random_driver".
    ns_role_mode: str = "no_driver_no_index"
    # EW role mode (parallel to ns_role_mode for E/W partnership).
    # "no_driver_no_index" (default), "east_drives", "west_drives", or "random_driver".
    ew_role_mode: str = "no_driver_no_index"

    # Bespoke subprofile matching maps (Phase 3).
    #
    # When set, these replace the default equal-index coupling with an explicit
    # driver→follower map.  Keys are 0-based driver subprofile indices; values
    # are lists of 0-based follower subprofile indices eligible to pair with
    # that driver sub.  Allows unequal subprofile counts between paired seats.
    #
    # None (default) = use standard index coupling (same index for both seats).
    ns_bespoke_map: Optional[Dict[int, List[int]]] = None
    ew_bespoke_map: Optional[Dict[int, List[int]]] = None

    subprofile_exclusions: List["SubprofileExclusionData"] = field(default_factory=list)

    # Explicit flag replacing magic profile name check (P1.1 refactor)
    # - is_invariants_safety_profile: bypass constraints for invariant tests
    is_invariants_safety_profile: bool = False

    # Optional display ordering — profiles with sort_order are listed at
    # that number (e.g. 20) instead of sequential position.  Profiles
    # without sort_order are numbered sequentially starting at 1.
    sort_order: Optional[int] = None

    def __post_init__(self) -> None:
        # Basic structural validation only. Cross-seat semantics are
        # handled in validate_profile() so tests can construct even
        # "bad" profiles and then explicitly validate them.
        if not self.profile_name:
            raise ProfileError("profile_name must not be empty.")
        if self.dealer not in ("N", "E", "S", "W"):
            raise ProfileError(f"Invalid dealer: {self.dealer}")
        if len(self.hand_dealing_order) != 4:
            raise ProfileError("hand_dealing_order must contain exactly 4 seats.")
        if set(self.hand_dealing_order) != {"N", "E", "S", "W"}:
            raise ProfileError("hand_dealing_order must be a permutation of N,E,S,W.")
        # NOTE: dealer-first in hand_dealing_order is no longer enforced.
        # Dealing order is auto-computed at runtime by the v2 builder
        # (_compute_dealing_order in deal_generator_v2.py).  The stored
        # hand_dealing_order is a display hint only.
        if self.tag not in ("Opener", "Overcaller"):
            raise ProfileError("tag must be 'Opener' or 'Overcaller'.")

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HandProfile":
        """
        Build a HandProfile from a JSON-like dict.

        This is the single entry point used by validate_profile() and
        by the test fixtures in tests/conftest.py.
        """

        # Seat profiles: each value is a SeatProfile dict.
        seat_profiles_dict = data.get("seat_profiles", {})
        seat_profiles: Dict[Seat, SeatProfile] = {}
        for seat, sp_data in seat_profiles_dict.items():
            seat_profiles[seat] = SeatProfile.from_dict(sp_data)

        # Subprofile exclusions (optional for legacy profiles).
        exclusions_raw = data.get("subprofile_exclusions", [])
        exclusions: List[SubprofileExclusionData] = [SubprofileExclusionData.from_dict(e) for e in exclusions_raw]

        # Use provided dealing order, or generate default (dealer + clockwise).
        dealer = str(data["dealer"])
        if "hand_dealing_order" in data:
            dealing_order = list(data["hand_dealing_order"])
        else:
            dealing_order = _default_dealing_order(dealer)

        # Bespoke maps: parse string keys → int, values → List[int].
        # None when absent (legacy/standard profiles).
        def _parse_bespoke_map(raw_map: Any) -> Optional[Dict[int, List[int]]]:
            if raw_map is None:
                return None
            if not isinstance(raw_map, dict):
                return None
            return {int(k): [int(v) for v in vals] for k, vals in raw_map.items()}

        ns_bespoke = _parse_bespoke_map(data.get("ns_bespoke_map"))
        ew_bespoke = _parse_bespoke_map(data.get("ew_bespoke_map"))

        return cls(
            profile_name=str(data["profile_name"]),
            description=str(data.get("description", "")),
            dealer=dealer,
            hand_dealing_order=dealing_order,
            tag=str(data["tag"]),
            seat_profiles=seat_profiles,
            author=str(data.get("author", "")),
            version=str(data.get("version", "")),
            # Legacy profiles may omit this – default to True.
            rotate_deals_by_default=bool(data.get("rotate_deals_by_default", True)),
            # Missing ns_role_mode in raw dict ⇒ treat as "no driver, no index".
            # validate_profile is responsible for rejecting unsupported values
            # when loading from arbitrary JSON.
            ns_role_mode=str(data.get("ns_role_mode", "no_driver_no_index") or "no_driver_no_index"),
            ew_role_mode=str(data.get("ew_role_mode", "no_driver_no_index") or "no_driver_no_index"),
            ns_bespoke_map=ns_bespoke,
            ew_bespoke_map=ew_bespoke,
            subprofile_exclusions=exclusions,
            # P1.1 refactor: explicit flags (default False for production profiles)
            is_invariants_safety_profile=bool(data.get("is_invariants_safety_profile", False)),
            # Optional display ordering (None = sequential position)
            sort_order=data.get("sort_order", None),
        )

    def ns_driver_seat(
        self,
        rng: Optional[random.Random] = None,
    ) -> Optional[Seat]:
        """
        Return a *metadata-level* preferred NS driver seat implied by ns_role_mode.

        This helper is used for UI / tests and is distinct from the per-board
        driver choice used by the deal generator.

        Semantics:

        - "north_drives"       -> "N"
        - "south_drives"       -> "S"
        - "random_driver":
            * if rng is provided, return rng.choice(["N", "S"])
            * if rng is None, return "N" (stable deterministic default)
        - "no_driver_no_index" -> None (explicit “no fixed driver” for legacy/default)
        - "no_driver"          -> None (explicit no-driver mode)
        - anything else        -> None (defensive fallback for unknown values)
        """
        mode = (self.ns_role_mode or "no_driver_no_index").lower()

        if mode == "north_drives":
            return "N"
        if mode == "south_drives":
            return "S"
        if mode == "random_driver":
            if rng is None:
                # Metadata-only usage without RNG: just pick N deterministically.
                return "N"
            return rng.choice(["N", "S"])
        if mode in ("no_driver", "no_driver_no_index"):
            return None

        # Unknown / future values: treat as "no driver"
        return None

    def ew_driver_seat(
        self,
        rng: Optional[random.Random] = None,
    ) -> Optional[Seat]:
        """
        Return a *metadata-level* preferred EW driver seat implied by ew_role_mode.

        Parallel to ns_driver_seat() but for the E-W partnership.

        Semantics:

        - "east_drives"        -> "E"
        - "west_drives"        -> "W"
        - "random_driver":
            * if rng is provided, return rng.choice(["E", "W"])
            * if rng is None, return "E" (stable deterministic default)
        - "no_driver_no_index" -> None (default)
        - "no_driver"          -> None
        - anything else        -> None (defensive fallback)
        """
        mode = (self.ew_role_mode or "no_driver_no_index").lower()

        if mode == "east_drives":
            return "E"
        if mode == "west_drives":
            return "W"
        if mode == "random_driver":
            if rng is None:
                return "E"
            return rng.choice(["E", "W"])
        if mode in ("no_driver", "no_driver_no_index"):
            return None

        # Unknown / future values: treat as "no driver"
        return None

    def ns_role_buckets(self) -> Dict[Seat, Dict[str, List[SubProfile]]]:
        """
        For NS seats only, group subprofiles into three buckets by ns_role_usage:

          - "driver":   subprofiles usable when the seat is the NS driver
          - "follower": subprofiles usable when the seat is the NS follower
          - "neutral":  subprofiles usable in either role (or with no metadata)

        EW seats are currently treated as neutral for Phase 3; we still
        return empty bucket dicts for completeness.
        """
        buckets: Dict[Seat, Dict[str, List[SubProfile]]] = {}

        for seat in ("N", "S"):
            sp = self.seat_profiles.get(seat)
            seat_buckets: Dict[str, List[SubProfile]] = {
                "driver": [],
                "follower": [],
                "neutral": [],
            }

            if sp is not None:
                for sub in sp.subprofiles:
                    # ns_role_usage is a declared field (default "any") — always present.
                    usage_lc = sub.ns_role_usage.lower()
                    if usage_lc == "driver_only":
                        seat_buckets["driver"].append(sub)
                    elif usage_lc == "follower_only":
                        seat_buckets["follower"].append(sub)
                    else:
                        # "any" or anything else we treat as neutral.
                        seat_buckets["neutral"].append(sub)

            buckets[seat] = seat_buckets

        # Ensure EW are present with empty buckets so callers don't need
        # special cases.  The loop above only populates N/S.
        for seat in ("E", "W"):
            buckets[seat] = {"driver": [], "follower": [], "neutral": []}

        return buckets

    def ew_role_buckets(self) -> Dict[Seat, Dict[str, List[SubProfile]]]:
        """
        For EW seats only, group subprofiles into three buckets by ew_role_usage:

          - "driver":   subprofiles usable when the seat is the EW driver
          - "follower": subprofiles usable when the seat is the EW follower
          - "neutral":  subprofiles usable in either role (or with no metadata)

        NS seats get empty bucket dicts for completeness.
        """
        buckets: Dict[Seat, Dict[str, List[SubProfile]]] = {}

        for seat in ("E", "W"):
            sp = self.seat_profiles.get(seat)
            seat_buckets: Dict[str, List[SubProfile]] = {
                "driver": [],
                "follower": [],
                "neutral": [],
            }

            if sp is not None:
                for sub in sp.subprofiles:
                    # ew_role_usage is a declared field (default "any") — always present.
                    usage_lc = sub.ew_role_usage.lower()
                    if usage_lc == "driver_only":
                        seat_buckets["driver"].append(sub)
                    elif usage_lc == "follower_only":
                        seat_buckets["follower"].append(sub)
                    else:
                        # "any" or anything else we treat as neutral.
                        seat_buckets["neutral"].append(sub)

            buckets[seat] = seat_buckets

        # Ensure NS are present with empty buckets so callers don't need
        # special cases.  The loop above only populates E/W.
        for seat in ("N", "S"):
            buckets[seat] = {"driver": [], "follower": [], "neutral": []}

        return buckets

    # ------------------------------------------------------------------
    # Persistence helpers (JSON-friendly dicts)
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "profile_name": self.profile_name,
            "description": self.description,
            "dealer": self.dealer,
            "hand_dealing_order": list(self.hand_dealing_order),
            "tag": self.tag,
            "author": self.author,
            "version": self.version,
            "rotate_deals_by_default": self.rotate_deals_by_default,
            "ns_role_mode": self.ns_role_mode,
            "ew_role_mode": self.ew_role_mode,
            "seat_profiles": {seat: sp.to_dict() for seat, sp in self.seat_profiles.items()},
            "subprofile_exclusions": [e.to_dict() for e in self.subprofile_exclusions],
            "is_invariants_safety_profile": self.is_invariants_safety_profile,
        }
        if self.sort_order is not None:
            d["sort_order"] = self.sort_order
        # Bespoke maps: emit with string keys (JSON requires string keys).
        # Only include when set (keeps JSON clean for profiles without bespoke maps).
        if self.ns_bespoke_map is not None:
            d["ns_bespoke_map"] = {str(k): v for k, v in self.ns_bespoke_map.items()}
        if self.ew_bespoke_map is not None:
            d["ew_bespoke_map"] = {str(k): v for k, v in self.ew_bespoke_map.items()}
        return d
