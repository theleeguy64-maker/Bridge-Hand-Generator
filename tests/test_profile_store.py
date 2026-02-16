# file: tests/test_profile_store.py
from __future__ import annotations

from pathlib import Path
import json

from bridge_engine.hand_profile import HandProfile
from bridge_engine import profile_store as ps


def make_dummy_profile() -> HandProfile:
    return HandProfile(
        profile_name="Dummy",
        description="Test profile",
        dealer="N",
        hand_dealing_order=["N", "E", "S", "W"],
        tag="Opener",
        seat_profiles={},
        author="Test",
        version="0.1",
    )


def test_profiles_dir_uses_custom_base(tmp_path):
    result = ps._profiles_dir(tmp_path)
    assert result.is_dir()
    assert result.parent == tmp_path
    assert result.name == ps.PROFILE_DIR_NAME


def test_save_and_load_profile_roundtrip(tmp_path, monkeypatch):
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    def fake_profiles_dir(base_dir: Path | None = None) -> Path:
        # ignore base_dir, always use our temp directory
        return profiles_dir

    monkeypatch.setattr(ps, "_profiles_dir", fake_profiles_dir)

    profile = make_dummy_profile()
    path = ps._profile_path_for(profile)
    ps._save_profile_to_path(profile, path)

    assert path.exists()
    data = json.loads(path.read_text())
    assert data["profile_name"] == "Dummy"

    loaded = ps._load_profiles()
    assert len(loaded) == 1
    loaded_path, loaded_profile = loaded[0]
    assert loaded_path == path
    assert isinstance(loaded_profile, HandProfile)
    assert loaded_profile.profile_name == "Dummy"
