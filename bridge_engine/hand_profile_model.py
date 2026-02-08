from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import random 

class ProfileError(Exception):
    """Raised when a hand profile or its constraints are invalid."""

# ---------------------------------------------------------------------------
# Low-level constraint building blocks
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubprofileExclusionClause:
    """A single clause in a subprofile exclusion rule."""
    group: str      # "ANY", "MAJOR", "MINOR"
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
    seat: str                          # "N", "E", "S", "W"
    subprofile_index: int              # 1-based
    excluded_shapes: Optional[list[str]] = None
    clauses: Optional[list[SubprofileExclusionClause]] = None

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
        clauses = (
            [SubprofileExclusionClause.from_dict(c) for c in clauses_raw]
            if clauses_raw is not None else None
        )
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
            raise ProfileError(
                f"Invalid subprofile index {self.subprofile_index} "
                f"for seat {self.seat}"
            )

        if self.excluded_shapes and self.clauses:
            raise ProfileError(
                "Exclusion may specify either excluded_shapes or clauses, not both"
            )

        if not self.excluded_shapes and not self.clauses:
            raise ProfileError(
                "Exclusion must specify excluded_shapes or clauses"
            )

        if self.excluded_shapes:
            seen: set[str] = set()
            for s in self.excluded_shapes:
                if s in seen:
                    raise ProfileError(f"Duplicate excluded shape: {s}")
                seen.add(s)

                if not (isinstance(s, str) and len(s) == 4 and s.isdigit()):
                    raise ProfileError(f"Invalid shape: {s}")
                digits = [int(c) for c in s]
                if sum(digits) != 13:
                    raise ProfileError(f"Shape does not sum to 13: {s}")

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
                    raise ProfileError(
                        f"Invalid count {c.count} for group {c.group}"
                    )

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
            raise ProfileError(
                f"SuitRange card bounds must be within 0–13, got "
                f"{self.min_cards}–{self.max_cards}."
            )
        if self.min_cards > self.max_cards:
            raise ProfileError(
                f"SuitRange min_cards cannot exceed max_cards "
                f"({self.min_cards}>{self.max_cards})."
            )
        if not (0 <= self.min_hcp <= 37 and 0 <= self.max_hcp <= 37):
            raise ProfileError(
                f"SuitRange HCP bounds must be within 0–37, got "
                f"{self.min_hcp}–{self.max_hcp}."
            )
        if self.min_hcp > self.max_hcp:
            raise ProfileError(
                f"SuitRange min_hcp cannot exceed max_hcp "
                f"({self.min_hcp}>{self.max_hcp})."
            )

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
                "total_min_hcp / total_max_hcp must be within 0–37 "
                f"(got {self.total_min_hcp}–{self.total_max_hcp})."
            )
        if self.total_min_hcp > self.total_max_hcp:
            raise ProfileError(
                "total_min_hcp cannot exceed total_max_hcp "
                f"({self.total_min_hcp}>{self.total_max_hcp})."
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
            raise ProfileError(
                f"SuitPairOverride.suits must contain exactly 2 suits, "
                f"got {len(self.suits)}."
            )
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
            raise ProfileError(
                f"required_suits_count must be positive, got {self.required_suits_count}."
            )
        if not self.allowed_suits:
            raise ProfileError("allowed_suits must not be empty.")
        allowed_set = set(self.allowed_suits)
        if not allowed_set.issubset({"S", "H", "D", "C"}):
            raise ProfileError(
                f"allowed_suits must be subset of {{S,H,D,C}}, got {self.allowed_suits}."
            )
        if self.required_suits_count > len(allowed_set):
            raise ProfileError(
                "required_suits_count cannot exceed number of distinct allowed_suits "
                f"({self.required_suits_count}>{len(allowed_set)})."
            )
        if len(self.suit_ranges) < self.required_suits_count:
            raise ProfileError(
                "suit_ranges must contain at least required_suits_count entries."
            )
        if self.required_suits_count != 2 and self.pair_overrides:
            raise ProfileError(
                "pair_overrides must be empty unless required_suits_count == 2."
            )

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
            pair_overrides=[
                SuitPairOverride.from_dict(d)
                for d in data.get("pair_overrides", [])
            ],
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

    Semantics implemented in Section C:
      • Let partner_suits = suits chosen by partner's RandomSuitConstraintData.
      • This hand must have at least one suit in partner_suits that satisfies suit_range.
    """

    partner_seat: str  # 'N', 'E', 'S', or 'W'
    suit_range: SuitRange

    def __post_init__(self) -> None:
        if self.partner_seat not in ("N", "E", "S", "W"):
            raise ProfileError(f"Invalid partner_seat: {self.partner_seat}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "partner_seat": self.partner_seat,
            "suit_range": self.suit_range.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> PartnerContingentData:
        return cls(
            partner_seat=str(data["partner_seat"]),
            suit_range=SuitRange.from_dict(data["suit_range"]),
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
    """

    opponent_seat: str  # 'N', 'E', 'S', or 'W'
    suit_range: SuitRange

    def __post_init__(self) -> None:
        if self.opponent_seat not in ("N", "E", "S", "W"):
            raise ProfileError(f"Invalid opponent_seat: {self.opponent_seat}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opponent_seat": self.opponent_seat,
            "suit_range": self.suit_range.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpponentContingentSuitData":
        return cls(
            opponent_seat=str(data["opponent_seat"]),
            suit_range=SuitRange.from_dict(data["suit_range"]),
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "standard": self.standard.to_dict(),
            "random_suit_constraint": (
                self.random_suit_constraint.to_dict()
                if self.random_suit_constraint is not None
                else None
            ),
            "partner_contingent_constraint": (
                self.partner_contingent_constraint.to_dict()
                if self.partner_contingent_constraint is not None
                else None
            ),
            "opponents_contingent_suit_constraint": (
                self.opponents_contingent_suit_constraint.to_dict()
                if self.opponents_contingent_suit_constraint is not None
                else None
            ),
            "weight_percent": self.weight_percent,
            # JSON field name for Phase 3 metadata.
            "ns_role_usage": getattr(self, "ns_role_usage", "any"),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubProfile":
        """
        Backwards compatible loader for SubProfile, including Phase 3 metadata.

        Supports both:
          - new-style "ns_role_usage" (preferred)
          - earlier experimental "ns_role_for_seat" (mapped to usage)
        """
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

        return cls(
            standard=StandardSuitConstraints.from_dict(data["standard"]),
            random_suit_constraint=(
                RandomSuitConstraintData.from_dict(rsc_data)
                if rsc_data is not None
                else None
            ),
            partner_contingent_constraint=(
                PartnerContingentData.from_dict(pc_data)
                if pc_data is not None
                else None
            ),
            opponents_contingent_suit_constraint=(
                OpponentContingentSuitData.from_dict(oc_data)
                if oc_data is not None
                else None
            ),
            weight_percent=float(data.get("weight_percent", 0.0)),
            ns_role_usage=ns_role_usage,
        )
        
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
            raise ProfileError(
                f"SeatProfile for seat {self.seat} must have at least one SubProfile."
            )

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
        A permutation of ["N", "E", "S", "W"], dealer must be first.
    tag
        "Opener" or "Overcaller".
    seat_profiles
        Mapping from seat ("N", "E", "S", "W") to SeatProfile.
    author
        Free text author (optional, default empty).
    version
        Free text version string (e.g. "0.2", optional, default empty).
   
    Full hand profile for one scenario.

    NOTE: ns_role_mode is a Phase-3 field controlling who “drives” the
    N-S partnership. For now it is metadata-only; generator logic still
    behaves as in Phase 2 when this is left at the default.
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
    # "north_drives" (default), "south_drives", or "random_driver".
    ns_role_mode: str = "north_drives"
    subprofile_exclusions: List["SubprofileExclusionData"] = field(default_factory=list)

    # Explicit flags replacing magic profile name checks (P1.1 refactor)
    # - is_invariants_safety_profile: bypass constraints for invariant tests
    # - use_rs_w_only_path: route to lightweight RS-W-only generator path
    is_invariants_safety_profile: bool = False
    use_rs_w_only_path: bool = False

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
            raise ProfileError(
                "hand_dealing_order must be a permutation of N,E,S,W."
            )
        if self.hand_dealing_order[0] != self.dealer:
            raise ProfileError(
                "First element of hand_dealing_order must be the dealer."
            )
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
        exclusions: List[SubprofileExclusionData] = [
            SubprofileExclusionData.from_dict(e) for e in exclusions_raw
        ]

        # Use provided dealing order, or generate default (dealer + clockwise).
        dealer = str(data["dealer"])
        if "hand_dealing_order" in data:
            dealing_order = list(data["hand_dealing_order"])
        else:
            dealing_order = _default_dealing_order(dealer)

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
            rotate_deals_by_default=bool(
                data.get("rotate_deals_by_default", True)
            ),
            # Missing ns_role_mode in raw dict ⇒ treat as "no driver, no index".
            # validate_profile is responsible for rejecting unsupported values
            # when loading from arbitrary JSON.
            ns_role_mode=str(
                data.get("ns_role_mode", "no_driver_no_index")
                or "no_driver_no_index"
            ),
            subprofile_exclusions=exclusions,
            # P1.1 refactor: explicit flags (default False for production profiles)
            is_invariants_safety_profile=bool(
                data.get("is_invariants_safety_profile", False)
            ),
            use_rs_w_only_path=bool(
                data.get("use_rs_w_only_path", False)
            ),
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
        mode = (
            getattr(self, "ns_role_mode", "no_driver_no_index")
            or "no_driver_no_index"
        ).lower()

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
                    # Preferred Phase 3 field.
                    usage = getattr(sub, "ns_role_usage", None)

                    if usage is None:
                        # Legacy experimental metadata: ns_role_for_seat
                        legacy_role = getattr(sub, "ns_role_for_seat", "neutral")
                        legacy_role = str(legacy_role).lower()
                        if legacy_role == "driver":
                            seat_buckets["driver"].append(sub)
                        elif legacy_role == "follower":
                            seat_buckets["follower"].append(sub)
                        else:
                            seat_buckets["neutral"].append(sub)
                        continue

                    usage_lc = str(usage).lower()
                    if usage_lc == "driver_only":
                        seat_buckets["driver"].append(sub)
                    elif usage_lc == "follower_only":
                        seat_buckets["follower"].append(sub)
                    else:
                        # "any" or anything else we treat as neutral.
                        seat_buckets["neutral"].append(sub)

            buckets[seat] = seat_buckets

        # Ensure EW are present with empty buckets so callers don't need
        # special cases.
        for seat in ("E", "W"):
            if seat not in buckets:
                buckets[seat] = {"driver": [], "follower": [], "neutral": []}

        return buckets    
        
    # ------------------------------------------------------------------
    # Persistence helpers (JSON-friendly dicts)
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "description": self.description,
            "dealer": self.dealer,
            "hand_dealing_order": list(self.hand_dealing_order),
            "tag": self.tag,
            "author": self.author,
            "version": self.version,
            "rotate_deals_by_default": getattr(self, "rotate_deals_by_default", True),
            # NEW: persist NS role mode, defaulting for legacy HandProfile objects
            "ns_role_mode": getattr(self, "ns_role_mode", "north_drives"),         
            "seat_profiles": {
                seat: sp.to_dict() for seat, sp in self.seat_profiles.items()
            },
            "subprofile_exclusions": [e.to_dict() for e in self.subprofile_exclusions],
        }
