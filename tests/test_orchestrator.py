# file: tests/test_orchestrator.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root (Exec) is on sys.path, same pattern as other tests
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bridge_engine import orchestrator  # type: ignore[import]
from bridge_engine import profile_cli  # type: ignore[import]


def test_profiles_dir_uses_given_base_dir(tmp_path: Path) -> None:
    """
    _profiles_dir should append PROFILE_DIR_NAME to the given base_dir.
    """
    base_dir = tmp_path
    profiles_dir = orchestrator._profiles_dir(base_dir)  # type: ignore[attr-defined]
    assert profiles_dir == base_dir / orchestrator.PROFILE_DIR_NAME  # type: ignore[attr-defined]


def test_discover_profiles_loads_profiles_using_handprofile(monkeypatch, tmp_path: Path) -> None:
    """
    _discover_profiles should scan the profiles directory, load JSON files,
    and return (Path, HandProfile) tuples.

    We stub HandProfile.from_dict so we don't depend on the full JSON schema.
    """
    profiles_dir = tmp_path / orchestrator.PROFILE_DIR_NAME  # type: ignore[attr-defined]
    profiles_dir.mkdir(parents=True)

    sample_file = profiles_dir / "sample.json"
    sample_file.write_text("{}", encoding="utf-8")

    # Stub HandProfile.from_dict to return a simple dummy object
    from bridge_engine import hand_profile as hp  # type: ignore[import]

    class DummyProfile:
        def __init__(self, name: str) -> None:
            self.profile_name = name

    def fake_from_dict(cls, data: Dict[str, Any]) -> DummyProfile:
        return DummyProfile("DummyProfile")

    monkeypatch.setattr(
        hp.HandProfile,
        "from_dict",
        classmethod(fake_from_dict),
        raising=True,
    )

    results = orchestrator._discover_profiles(base_dir=tmp_path)  # type: ignore[attr-defined]

    assert len(results) == 1
    path, profile = results[0]
    assert path == sample_file
    assert isinstance(profile, DummyProfile)
    assert profile.profile_name == "DummyProfile"


def test_choose_profile_for_session_returns_none_when_no_profiles(monkeypatch, capsys) -> None:
    """
    If no profiles exist on disk, _choose_profile_for_session should return None
    and prompt the user to create one via Profile Management.
    """

    def fake_discover() -> List[tuple[Path, Any]]:
        return []

    monkeypatch.setattr(orchestrator, "_discover_profiles", fake_discover, raising=True)

    result = orchestrator._choose_profile_for_session()  # type: ignore[attr-defined]
    captured = capsys.readouterr()

    assert result is None
    assert "No profiles found" in captured.out


def test_choose_profile_for_session_allows_cancel(monkeypatch, capsys) -> None:
    """
    If the user presses Enter at the profile selection prompt, the function
    should cancel and return None.
    """

    class DummyProfile:
        def __init__(self, name: str) -> None:
            self.profile_name = name
            self.version = "0.1"
            self.tag = "Opener"
            self.dealer = "N"
            self.sort_order = None

    dummy_profile = DummyProfile("ProfileOne")
    dummy_path = Path("dummy.json")

    def fake_discover() -> List[tuple[Path, DummyProfile]]:
        return [(dummy_path, dummy_profile)]

    monkeypatch.setattr(orchestrator, "_discover_profiles", fake_discover, raising=True)

    # First (and only) call to input() returns empty string → cancel.
    inputs = iter([""])

    def fake_input(prompt: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input, raising=True)

    result = orchestrator._choose_profile_for_session()  # type: ignore[attr-defined]
    captured = capsys.readouterr()

    assert result is None
    assert "Cancelled profile selection." in captured.out


def test_main_menu_exit_on_zero(monkeypatch, capsys) -> None:
    """
    main_menu should exit cleanly when the user chooses option '0'.
    It must not call profile management or deal generation in that case.
    """
    called = {"profile_management": 0, "deal_generation": 0}

    def fake_profile_management() -> None:
        called["profile_management"] += 1

    def fake_deal_generation_session() -> None:
        called["deal_generation"] += 1

    monkeypatch.setattr(profile_cli, "run_profile_manager", fake_profile_management, raising=True)
    monkeypatch.setattr(
        orchestrator,
        "_run_deal_generation_session",
        fake_deal_generation_session,
        raising=True,
    )

    # First call to input() → "0" (Exit)
    inputs = iter(["0"])

    def fake_input(prompt: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input, raising=True)

    orchestrator.main_menu()
    captured = capsys.readouterr()

    assert "Exiting" in captured.out
    assert called["profile_management"] == 0
    assert called["deal_generation"] == 0


def test_run_deal_generation_session_happy_path(monkeypatch, tmp_path: Path, capsys) -> None:
    """
    Full happy-path integration test for _run_deal_generation_session:

    - Chooses a profile.
    - Validates it (via validate_profile).
    - Calls run_setup with correct arguments.
    - Calls generate_deals with setup/profile/num_deals.
    - Calls render_deals and prints a session summary.
    """

    # --- Dummy profile selected by _choose_profile_for_session ---
    class DummyProfile:
        def __init__(self, name: str) -> None:
            self.profile_name = name
            self.version = "0.1"
            self.tag = "Opener"
            self.dealer = "N"
            self.rotate_deals_by_default = True

    dummy_profile = DummyProfile("Defense to Weak 2s")

    chosen = {"called": False}

    def fake_choose() -> DummyProfile:
        chosen["called"] = True
        return dummy_profile

    monkeypatch.setattr(orchestrator, "_choose_profile_for_session", fake_choose, raising=True)

    # --- validate_profile stub: just echo the profile back ---
    validated = {"called": False}

    def fake_validate(profile: Any) -> Any:
        validated["called"] = True
        return profile

    monkeypatch.setattr(orchestrator, "validate_profile", fake_validate, raising=True)

    # --- run_setup stub: capture arguments and return a simple SetupStub ---
    class SetupStub:
        def __init__(self, base_dir: Path) -> None:
            self.base_dir = base_dir
            self.txt_dir = base_dir / "txt"
            self.lin_dir = base_dir / "lin"
            self.log_dir = base_dir / "logs"

    setup_called: Dict[str, Any] = {}

    def fake_run_setup(*, base_dir: Path, owner: str, profile_name: str, ask_seed_choice: bool) -> SetupStub:
        setup_called["base_dir"] = base_dir
        setup_called["owner"] = owner
        setup_called["profile_name"] = profile_name
        setup_called["ask_seed_choice"] = ask_seed_choice
        return SetupStub(base_dir)

    monkeypatch.setattr(orchestrator, "run_setup", fake_run_setup, raising=True)

    # --- generate_deals stub: capture inputs and return a dummy DealSet ---
    class DummyDealSet:
        pass

    deals_called: Dict[str, Any] = {}

    def fake_generate_deals(
        setup: Any,
        profile: Any,
        num_deals: int,
        enable_rotation: bool = True,
    ) -> DummyDealSet:
        deals_called["setup"] = setup
        deals_called["profile"] = profile
        deals_called["num_deals"] = num_deals
        deals_called["enable_rotation"] = enable_rotation
        return DummyDealSet()

    monkeypatch.setattr(orchestrator, "generate_deals", fake_generate_deals, raising=True)

    # --- render_deals stub: capture inputs and return a summary object ---
    class SummaryStub:
        def __init__(self, base_dir: Path) -> None:
            self.num_deals = 4
            self.txt_path = base_dir / "out.txt"
            self.lin_path = base_dir / "out.lin"
            self.warnings: List[str] = []

    render_called: Dict[str, Any] = {}

    def fake_render_deals(
        *,
        setup: Any,
        profile: Any,
        deal_set: Any,
        print_to_console: bool,
        append_txt: bool,
    ) -> SummaryStub:
        render_called["setup"] = setup
        render_called["profile"] = profile
        render_called["deal_set"] = deal_set
        render_called["print_to_console"] = print_to_console
        render_called["append_txt"] = append_txt
        return SummaryStub(setup.base_dir)

    monkeypatch.setattr(orchestrator, "render_deals", fake_render_deals, raising=True)

    # --- User input sequence for the session parameters ---
    # 1) Owner name (press Enter → default "Lee")
    # 2) Base output directory (explicit path)
    # 3) Number of deals (e.g. "4")
    base_dir_str = str(tmp_path)
    inputs = iter(["", base_dir_str, "4", ""])  # extra "" answers the rotation Y/n

    def fake_input(prompt: str = "") -> str:
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input, raising=True)

    # --- Run the session ---
    orchestrator._run_deal_generation_session()  # type: ignore[attr-defined]
    out = capsys.readouterr().out

    # --- Assertions on orchestrator behaviour ---
    assert chosen["called"] is True
    assert validated["called"] is True

    # run_setup called with values from prompts
    assert setup_called["owner"] == "Lee"  # default owner
    assert setup_called["profile_name"] == dummy_profile.profile_name
    assert setup_called["ask_seed_choice"] is True
    # base_dir resolved from the user input
    assert setup_called["base_dir"].resolve() == Path(base_dir_str).resolve()

    # generate_deals called with correct arguments
    assert isinstance(deals_called["setup"], SetupStub)
    assert deals_called["profile"] is dummy_profile
    assert deals_called["num_deals"] == 4

    # render_deals called with expected flags and deal_set
    assert isinstance(render_called["deal_set"], DummyDealSet)
    assert render_called["print_to_console"] is True
    assert render_called["append_txt"] is False

    # Session summary printed
    assert "=== Session complete ===" in out
    assert "Profile       : Defense to Weak 2s" in out
    assert "Deals created : 4" in out
