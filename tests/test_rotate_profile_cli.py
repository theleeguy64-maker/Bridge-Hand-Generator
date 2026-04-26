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
    import bridge_engine.rotate_profile as rp_mod
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(rp_mod, "validate_profile", lambda profile: None)
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
    import bridge_engine.rotate_profile as rp_mod
    from bridge_engine.rotate_profile import main

    monkeypatch.setattr(profile_store, "_project_root", lambda: tmp_path)
    monkeypatch.setattr(rp_mod, "validate_profile", lambda profile: None)
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
