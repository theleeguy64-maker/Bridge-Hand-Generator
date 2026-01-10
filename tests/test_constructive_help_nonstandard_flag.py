# tests/test_constructive_help_nonstandard_flag.py

from bridge_engine import deal_generator


def test_nonstandard_constructive_help_flag_defaults_off() -> None:
    """
    Sanity check: the non-standard constructive-help flag must be OFF by default.

    This ensures that any future RS/PC/OC-aware constructive helper cannot
    accidentally activate without an explicit opt-in change (and test update).
    """
    assert deal_generator.ENABLE_CONSTRUCTIVE_HELP_NONSTANDARD is False


def test_nonstandard_constructive_helper_gate_is_false_for_safety_profile() -> None:
    """
    Even if someone flips the global flag in the future, invariants-safety
    profiles must never see non-standard constructive help.
    """
    class _DummySafetyProfile:
        # Duck-typed shape: _nonstandard_constructive_help_enabled only cares
        # about this flag at the moment.
        is_invariants_safety_profile = True

    profile = _DummySafetyProfile()
    assert deal_generator._nonstandard_constructive_help_enabled(profile) is False  # type: ignore[attr-defined]


# Optional: future sandbox factory for RS+PC v2 work.
# This is intentionally unused for now; it just gives us a named test-only
# profile we can hook up once we start experimenting with non-standard
# constructive help.
def make_rs_pc_sandbox_profile():
    """
    Minimal duck-typed RS+PC sandbox profile for future v2 experiments.

    For now, this is *only* a factory. We do not feed it into the real deal
    generator yet; that will be done explicitly under the v2 flag.
    """

    class _DummySubprofile:
        def __init__(self, is_rs: bool = False) -> None:
            if is_rs:
                # Presence of this attribute marks the seat as "Random Suit"
                # for the constrained loop.
                self.random_suit_constraint = object()

    class _DummySeatProfile:
        def __init__(self, is_rs: bool = False) -> None:
            self.subprofiles = [_DummySubprofile(is_rs=is_rs)]

    class _DummyProfile:
        def __init__(self) -> None:
            # Treat N as a potential PC seat later; W/E as RS seats.
            self.dealer = "N"
            self.hand_dealing_order = ["N", "E", "S", "W"]
            self.seat_profiles = {
                "N": _DummySeatProfile(is_rs=False),
                "E": _DummySeatProfile(is_rs=True),
                "S": _DummySeatProfile(is_rs=False),
                "W": _DummySeatProfile(is_rs=True),
            }
            # Ensure NS coupling never triggers in this sandbox.
            self.ns_index_coupling_enabled = False
            self.profile_name = "RS_PC_nonstandard_sandbox"

    return _DummyProfile()


def test_rs_pc_sandbox_profile_factory_smoke() -> None:
    """
    Smoke test only: we can construct the RS+PC sandbox profile and it has
    the expected basic shape. This does *not* touch the core deal generator.
    """
    profile = make_rs_pc_sandbox_profile()
    assert getattr(profile, "profile_name", "") == "RS_PC_nonstandard_sandbox"
    assert set(profile.seat_profiles.keys()) == {"N", "E", "S", "W"}