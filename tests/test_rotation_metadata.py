import bridge_engine.orchestrator as orchestrator
import bridge_engine.profile_wizard as profile_wizard


# ---------------------------------------------------------------------------
# Orchestrator: rotation default comes from profile metadata
# ---------------------------------------------------------------------------


def test_run_deal_generation_uses_profile_rotation_default(monkeypatch):
    """
    If the profile has rotate_deals_by_default=False, that value should be used
    as the default for the rotation yes/no prompt.
    """

    class FakeProfile:
        def __init__(self, rotate: bool):
            self.profile_name = "Test Profile"
            self.rotate_deals_by_default = rotate

    chosen_profile = FakeProfile(rotate=False)

    # --- Stub out the heavy dependencies so we don't hit the real system ---
    monkeypatch.setattr(
        orchestrator, "_choose_profile_for_session", lambda: chosen_profile
    )
    monkeypatch.setattr(orchestrator, "validate_profile", lambda profile: profile)

    # Generic text input: just echo the default value back
    monkeypatch.setattr(
        orchestrator, "_input_with_default", lambda prompt, default: default
    )

    # Number-of-deals prompt
    monkeypatch.setattr(
        orchestrator,
        "_input_int_with_default",
        lambda prompt, default, minimum=1: 5,
    )

    class FakeSetup:
        pass

    class FakeDealSet:
        pass

    class FakeSummary:
        def __init__(self):
            self.num_deals = 5
            self.txt_path = "out/txt/fake.txt"
            self.lin_path = "out/lin/fake.lin"
            self.warnings = []  # orchestrator checks `if summary.warnings`

    monkeypatch.setattr(orchestrator, "run_setup", lambda **kwargs: FakeSetup())
    monkeypatch.setattr(orchestrator, "generate_deals", lambda **kwargs: FakeDealSet())
    monkeypatch.setattr(orchestrator, "render_deals", lambda **kwargs: FakeSummary())

    calls = {}

    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        # Capture the last call for assertions.
        calls["prompt"] = prompt
        calls["default"] = default
        return default

    monkeypatch.setattr(orchestrator, "_yes_no", fake_yes_no)

    orchestrator._run_deal_generation_session()

    assert "Randomly rotate deals" in str(
        calls["prompt"]
    ), "Expected rotation yes/no prompt"
    # The default passed into _yes_no should reflect rotate_deals_by_default=False.
    assert calls["default"] is False


def test_run_deal_generation_defaults_rotation_true_if_missing(monkeypatch):
    """
    If the profile has no rotate_deals_by_default attribute (old JSON),
    the orchestrator should fall back to default=True.
    """

    class FakeProfile:
        def __init__(self):
            self.profile_name = "Legacy Profile"
            # No rotate_deals_by_default attribute on purpose.

    chosen_profile = FakeProfile()

    monkeypatch.setattr(
        orchestrator, "_choose_profile_for_session", lambda: chosen_profile
    )
    monkeypatch.setattr(orchestrator, "validate_profile", lambda profile: profile)
    monkeypatch.setattr(
        orchestrator, "_input_with_default", lambda prompt, default: default
    )

    monkeypatch.setattr(
        orchestrator,
        "_input_int_with_default",
        lambda prompt, default, minimum=1: 5,
    )

    class FakeSetup:
        pass

    class FakeDealSet:
        pass

    class FakeSummary:
        def __init__(self):
            self.num_deals = 5
            self.txt_path = "out/txt/fake.txt"
            self.lin_path = "out/lin/fake.lin"
            self.warnings = []

    monkeypatch.setattr(orchestrator, "run_setup", lambda **kwargs: FakeSetup())
    monkeypatch.setattr(orchestrator, "generate_deals", lambda **kwargs: FakeDealSet())
    monkeypatch.setattr(orchestrator, "render_deals", lambda **kwargs: FakeSummary())

    calls = {}

    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        calls["prompt"] = prompt
        calls["default"] = default
        return default

    monkeypatch.setattr(orchestrator, "_yes_no", fake_yes_no)

    orchestrator._run_deal_generation_session()

    assert "Randomly rotate deals" in str(calls["prompt"])
    # With no attribute present, getattr(..., "rotate_deals_by_default", True)
    # should pass default=True into _yes_no.
    assert calls["default"] is True


# ---------------------------------------------------------------------------
# Profile wizard: rotation prompt + HandProfile wiring
# ---------------------------------------------------------------------------


def test_create_profile_interactive_sets_rotate_flag(monkeypatch):
    """
    create_profile_interactive should:
      - ask 'Rotate deals by default?' with default=True
      - pass the chosen value into HandProfile(rotate_deals_by_default=...)
    """

    created_kwargs = {}

    class DummyHandProfile:
        def __init__(self, **kwargs):
            created_kwargs.update(kwargs)

    # Replace HandProfile + validation so we don't depend on the real model.
    monkeypatch.setattr(profile_wizard, "HandProfile", DummyHandProfile)
    monkeypatch.setattr(profile_wizard, "validate_profile", lambda profile: None)

    # Stub basic metadata prompts.
    def fake_input_with_default(prompt: str, default: str) -> str:
        if "Profile name" in prompt:
            return "Test Profile"
        if "Description" in prompt:
            return "Test Description"
        if prompt.startswith("Author"):
            return "Tester"
        if prompt.startswith("Version"):
            return "1.0"
        # Dealing order custom input is skipped because we accept the default order.
        return default

    monkeypatch.setattr(
        profile_wizard, "_input_with_default", fake_input_with_default
    )

    def fake_input_choice(prompt: str, options, default: str) -> str:
        if "Tag" in prompt:
            return "Opener"
        if "Dealer seat" in prompt:
            return "N"
        return default

    monkeypatch.setattr(profile_wizard, "_input_choice", fake_input_choice)

    # Fake seat profiles: type doesn't matter, HandProfile stub just records kwargs.
    def fake_build_seat_profile(seat: str):
        return f"SeatProfile-{seat}"

    monkeypatch.setattr(profile_wizard, "_build_seat_profile", fake_build_seat_profile)

    calls = []

    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        calls.append((prompt, default))
        # Accept default dealing order, but choose False for rotation.
        if "Rotate deals by default" in prompt:
            return False
        return True

    monkeypatch.setattr(profile_wizard, "_yes_no", fake_yes_no)

    profile_wizard.create_profile_interactive()

    # Find the rotation prompt call.
    rotate_calls = [
        (p, d) for (p, d) in calls if "Rotate deals by default" in p
    ]
    assert rotate_calls, "Expected a 'Rotate deals by default?' prompt"
    _, default = rotate_calls[-1]
    assert default is True, "New profiles should default rotation to True"

    # And ensure our chosen value went into the HandProfile constructor.
    assert created_kwargs.get("rotate_deals_by_default") is False


def test_edit_constraints_interactive_uses_existing_rotation_default(monkeypatch):
    """
    edit_constraints_interactive should:
      - default the rotation prompt from existing.rotate_deals_by_default (or True)
      - pass the chosen value into the new HandProfile.
    """

    class DummyExisting:
        def __init__(self):
            self.profile_name = "Existing Profile"
            self.description = "Existing Desc"
            self.tag = "Opener"
            self.dealer = "N"
            self.hand_dealing_order = ["N", "E", "S", "W"]
            self.seat_profiles = {
                "N": "N-profile",
                "E": "E-profile",
                "S": "S-profile",
                "W": "W-profile",
            }
            self.author = "Author"
            self.version = "0.1"
            self.rotate_deals_by_default = False

    created_kwargs = {}

    class DummyHandProfile:
        def __init__(self, **kwargs):
            created_kwargs.update(kwargs)

    monkeypatch.setattr(profile_wizard, "HandProfile", DummyHandProfile)
    monkeypatch.setattr(profile_wizard, "validate_profile", lambda profile: None)

    calls = []

    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        calls.append((prompt, default))
        if "Do you want to edit constraints for seat" in prompt:
            # Keep existing seat profiles — we don't care about changing them here.
            return False
        if "Rotate deals by default" in prompt:
            # Flip the flag to True.
            return True
        return default

    monkeypatch.setattr(profile_wizard, "_yes_no", fake_yes_no)

    existing = DummyExisting()
    profile_wizard.edit_constraints_interactive(existing)

    rotate_calls = [
        (p, d) for (p, d) in calls if "Rotate deals by default" in p
    ]
    assert rotate_calls, "Expected a 'Rotate deals by default?' prompt in edit flow"
    _, default = rotate_calls[-1]
    # Default should come from existing.rotate_deals_by_default (False).
    assert default is existing.rotate_deals_by_default is False

    # The new HandProfile should receive the user's chosen value (True).
    assert created_kwargs.get("rotate_deals_by_default") is True


def test_edit_constraints_interactive_defaults_rotation_true_if_missing(monkeypatch):
    """
    Backwards compat: if existing has no rotate_deals_by_default attribute,
    the default in the prompt should be True.
    """

    class LegacyExisting:
        def __init__(self):
            self.profile_name = "Legacy Profile"
            self.description = "Desc"
            self.tag = "Opener"
            self.dealer = "N"
            self.hand_dealing_order = ["N", "E", "S", "W"]
            self.seat_profiles = {
                "N": "N-profile",
                "E": "E-profile",
                "S": "S-profile",
                "W": "W-profile",
            }
            self.author = "Author"
            self.version = "0.1"
            # No rotate_deals_by_default attribute on purpose.

    class DummyHandProfile:
        def __init__(self, **kwargs):
            # We don't need to inspect kwargs here.
            pass

    monkeypatch.setattr(profile_wizard, "HandProfile", DummyHandProfile)
    monkeypatch.setattr(profile_wizard, "validate_profile", lambda profile: None)

    calls = []

    def fake_yes_no(prompt: str, default: bool = True) -> bool:
        calls.append((prompt, default))
        if "Do you want to edit constraints for seat" in prompt:
            return False
        if "Rotate deals by default" in prompt:
            return default
        return default

    monkeypatch.setattr(profile_wizard, "_yes_no", fake_yes_no)

    existing = LegacyExisting()
    profile_wizard.edit_constraints_interactive(existing)

    rotate_calls = [
        (p, d) for (p, d) in calls if "Rotate deals by default" in p
    ]
    assert rotate_calls, "Expected rotation prompt even for legacy profiles"
    _, default = rotate_calls[-1]
    # getattr(existing, "rotate_deals_by_default", True) -> True
    assert default is True
