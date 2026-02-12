# tests/test_constructive_help_nonstandard_flag.py

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