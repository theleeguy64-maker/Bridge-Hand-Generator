"""CLI tests for bridge_engine.rotate_profile.main()."""

from __future__ import annotations

import json
from pathlib import Path


def _write_profile_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_cli_success_exit_0_writes_file(tmp_path, make_profile_dict, monkeypatch):
    from bridge_engine import profile_store
    import bridge_engine.rotate_profile as rp_mod
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    # The canonical fixture has a PC/RS cross-seat dependency that does not
    # survive rotation (N's PC partner "S" → E's PC partner "W", but W lacks
    # RS after rotation).  CLI tests exercise the I/O path, not validation.
    monkeypatch.setattr(rp_mod, "validate_profile", lambda profile: None)

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
    import bridge_engine.rotate_profile as rp_mod
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(rp_mod, "validate_profile", lambda profile: None)

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
