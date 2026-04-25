# Rotate Profile — Design Spec

**Date:** 2026-04-25
**Status:** Draft — pending user review (review triage applied 2026-04-25)
**Branch:** `cleanup/cli-menu/Test`

## Purpose

Provide a one-shot way to produce a "role-flipped" copy of an existing hand profile by rotating every seat reference one position around the table: **W → N → E → S → W**.

The driving use case: profiles currently authored as "opps open / we overcall" can be turned into "we open / opps overcall" variants without re-authoring constraints by hand. Constraint shapes (HCP, suit lengths, contingents) carry over unchanged; only the seat *labels* rotate.

> Note: rotation is mechanically safe in this app because constraints are purely about cards held (HCP, shape, contingents) — no constraint depends on auction position, vulnerability, or any dealer-relative property.

## Scope

**In scope (now):**
- A pure rotation function `rotate_profile(profile_dict) -> dict`.
- A thin CLI wrapper: `python -m bridge_engine.rotate_profile <input.json> [...]`.
- An entry in the **Admin** submenu of the running app (Profile rotation), which prompts for a source profile from the existing list and runs the same rotation pipeline.
- Validation of the rotated profile via existing `HandProfile.from_dict()` + `validate_profile()`.
- Algorithmic swap of `profile_name` halves; filename derived from the new `profile_name`; provenance via a new `rotated_from` field.
- Refusal to re-rotate an already-rotated profile (detected via `rotated_from`).
- Unit + integration tests covering rotation rules, exit codes, CLI surface, and the menu entry.

**Out of scope (later, if generalised):**
- Configurable rotation direction or arbitrary rotations (always +1 around the cycle for now).
- Batch mode (single input file per invocation).
- `--dry-run` preview mode (delete the file if wrong).
- Live-deal smoke test (the wrong-API blocker resolved by dropping the smoke step; structural validation is sufficient).
- Statistical preservation testing (HCP histograms across N deals before/after rotation). Manual verification covers this with eyeballing.

## Architecture

One new module: `bridge_engine/rotate_profile.py`. One small change to `bridge_engine/orchestrator.py` to add a menu entry.

The architecture diagram below shows the public surface only. Helper-function decomposition is an implementation detail and may evolve in the implementation plan.

```
rotate_profile.py
├── ROTATE_MAP = {"W": "N", "N": "E", "E": "S", "S": "W"}
├── rotate_profile(profile_dict, *, new_name=None, new_description=None) -> dict
│     pure function — does NOT mutate input. Returns a deep-copied, rotated dict.
├── run_rotation_menu()  # interactive entry for the Admin submenu
└── main(argv: list[str] | None = None) -> int  # CLI entry
        + if __name__ == "__main__": sys.exit(main())
```

`orchestrator.py` adds one entry to `admin_menu()`: `("Rotate a profile", rotate_profile.run_rotation_menu)`.

**Pipeline (CLI mode):**

1. Load source JSON → dict.
2. `rotate_profile(dict)` returns rotated dict (input dict is never mutated).
3. Validation: `HandProfile.from_dict(rotated)` + `validate_profile(profile)` — catches structural errors.
4. Write to `<project_root>/profiles/<derived-or-overridden-filename>.json`.

The output directory is resolved relative to the project root via `Path(__file__).resolve().parents[1] / "profiles"` — matching the existing `profile_store._profiles_dir()` convention. **Output is not cwd-dependent.**

File I/O matches the existing `profile_store` writer exactly: UTF-8 encoding, indent=2, `sort_keys=True`, trailing newline, written atomically via `tmp + os.replace`.

## Rotation Rules

`R(seat)` = `ROTATE_MAP[seat]`, i.e. W→N, N→E, E→S, S→W.

### Top-level fields

| Field | Action |
|---|---|
| `dealer` | `R(dealer)` |
| `hand_dealing_order` | apply `R` to each seat in list |
| `seat_profiles` | rekey: `{seat: profile}` → `{R(seat): profile_with_seat_field_updated}` |
| `subprofile_exclusions` | for each entry, rotate `seat` field via `R(seat)` |
| `ns_linked_profile` ↔ `ew_linked_profile` | **swap positions**, then rotate `primary_seat` inside each |
| `tag` | **carry over verbatim**. Rationale: `tag` (`Opener`/`Overcaller`) describes the role of the *hand*, not the seat. The whole profile's auction structure rotates together with the hands, so the tag value travels with the profile unchanged. |
| `profile_name` | **algorithmic swap** (see "Profile-name swap algorithm" below); default unless `--name` overrides |
| `description` | **carry over verbatim**. Rationale: descriptions describe the convention (Cappeletti, TO Dbl, etc.), not who's sitting where. |
| `version` | **reset to `"0.1"`**. The rotated profile is a new profile and starts fresh. |
| `schema_version`, `sort_order` | carry over verbatim |
| `category`, `author`, `rotate_deals_by_default`, `is_invariants_safety_profile` | carry over verbatim. Rationale: profile-wide flags/strings that don't encode seat semantics. |
| `rotated_from` | **set to the source filename** (without directory). Provenance marker. |
| Legacy fields (`ns_role_mode`, `ew_role_mode`, `ns_bespoke_map`, `ew_bespoke_map`) | **stripped** from the rotated output. These are dormant in current profiles and `from_dict` ignores them; carrying them forward would propagate stale references. |
| Other unknown top-level keys | carry over verbatim |

### Inside each `SeatProfile`

| Field | Action |
|---|---|
| `seat` | `R(seat)` |
| `subprofiles` | each subprofile rotated (see below) |

### Inside each `SubProfile`

| Field | Action |
|---|---|
| `partner_contingent_constraint.partner_seat` | `R(partner_seat)` if present |
| `opponents_contingent_suit_constraint.opponent_seat` | `R(opponent_seat)` if present |
| `name`, `weight_percent`, `standard`, `random_suit_constraint`, etc. | unchanged |

### Inside each `LinkedProfile` (after the NS↔EW swap)

| Field | Action |
|---|---|
| `primary_seat` | `R(primary_seat)` |
| `subprofile_map` | unchanged — both keys (primary subprofile index) and values (lists of secondary subprofile indices) are integer-keyed, not seat-keyed |

### Why NS↔EW swap?

After a +1 rotation, the seats that used to be E and W are now S and N (the new NS pair). So whatever pair-coupling logic was in `ew_linked_profile` now describes the new NS pair, and vice versa. The two linked-profile slots in the JSON literally swap.

When only one slot is populated (the other is `None`), the populated slot moves to the other position and `None` takes its place. When both are `None`, neither moves.

### Mutation contract

`rotate_profile` does NOT mutate the input dict. The function deep-copies the input, applies rotation in place on the copy, and returns the copy.

### Profile-name swap algorithm

Two-step pronoun swap on `profile_name`:

1. **Normalise:** replace every whole-word `Our` with `We` and every whole-word `our` with `we`.
2. **Swap:** swap whole-word `Opps` ↔ `We` and `opps` ↔ `we` throughout the string.

"Whole-word" means surrounded by word boundaries, so `Open` is not affected by the `Our` → `We` step. Both replacements are case-sensitive (the case-preserving pair `Our/our` and `Opps/opps`/`We/we` is handled by running each pair separately).

If the resulting name is byte-identical to the source (no `Opps`/`We`/`Our`/`our`/`opps`/`we` tokens were present), refuse with exit 2: `Source profile_name does not contain Opps/We/Our pronouns to swap; supply --name explicitly.`

Worked examples (the four target profiles):

| Source | After normalise | Output |
|---|---|---|
| `Opps Open Strong 1NT and we Overcall Cappeletti` | (unchanged) | `We Open Strong 1NT and Opps Overcall Cappeletti` |
| `Opps Open 3 Weak 2s and we Compete` | (unchanged) | `We Open 3 Weak 2s and Opps Compete` |
| `Opps Open & Our TO Dbl` | `Opps Open & We TO Dbl` | `We Open & Opps TO Dbl` |
| `Opps Open & Our TO Dbl Balancing` | `Opps Open & We TO Dbl Balancing` | `We Open & Opps TO Dbl Balancing` |

`--name "X"` bypasses the algorithm entirely.

### Filename derivation

- The output filename is derived from the new `profile_name` (algorithmic or `--name` override) via the project's standard slugification: spaces → underscores, `&` preserved literally, plus the version suffix `_v0.1.json`.
- `--output <path>` bypasses derivation.

### Already-rotated input

If the source profile has a non-null `rotated_from` field, refuse with exit 2: `Source is already a rotated profile (rotated_from: <X>); rotation refused.` This prevents accumulating rotations and accidental double-rotation.

## Validation, Errors

**Validation step (after rotation, before writing):**
- Call `HandProfile.from_dict(rotated_dict)`. Catches structural errors at the dataclass level.
- Then call `validate_profile(profile)` from `hand_profile_validate.py`. Catches cross-cutting checks (linked-profile surjectivity, exhaustivity, bounds).
- If either raises `ProfileError`, abort with `Rotation produced invalid profile: <error>` on stderr. **Do not write the file.**
- Other exceptions (`KeyError`, `TypeError`, etc.) from malformed input also abort with exit code 2.

**Error policy:**

| Cause | Exit code | Message (stderr) |
|---|---|---|
| Success | 0 | (success summary on stdout — see below) |
| File not found / bad JSON on input | 1 | propagated underlying error |
| Source already rotated (`rotated_from` non-null) | 2 | `Source is already a rotated profile (rotated_from: <X>); rotation refused.` |
| Source `profile_name` has no swappable pronouns | 2 | `Source profile_name does not contain Opps/We/Our pronouns to swap; supply --name explicitly.` |
| Validation failure on rotated profile | 2 | `Rotation produced invalid profile: <error>` |
| Output file already exists, no `--force` | 4 | `Output exists: <path>. Pass --force to overwrite.` |
| Argparse / bad CLI args | 2 (argparse default) | argparse error text |

> Exit code 3 was reserved for smoke-test failure; the smoke step has been dropped from this spec, so exit code 3 is unused. Reserved for future use.

**Success summary (stdout):**
On exit 0, print one line: `Rotated: dealer <S> → <R(S)>, NS↔EW linked profiles swapped, <N> seat profiles rekeyed. Wrote <output_path>.`

**Undo:** to undo a rotation, delete the output file. The source is never modified.

**CLI surface:**
```
python -m bridge_engine.rotate_profile <input.json>
                                       [--name "We Open ..."]
                                       [--description "..."]
                                       [--output <path>]      # full override of derived filename
                                       [--force]              # overwrite existing output
```

`argparse`'s default `--help` is used (no custom help block).

> **Note on `&` in filenames:** profile filenames containing `&` (e.g. `Opps_Open_&_Our_TO_Dbl_v0.9.json`) must be shell-quoted on invocation, otherwise zsh/bash will interpret `&` as a job-control operator. Either single-quote the path or escape with backslash. The rotator preserves `&` literally in derived filenames.

## Testing

### Unit tests (`tests/test_rotate_profile.py`)

Fixtures: a single `make_profile_dict()` factory in `conftest.py` produces a canonical example dict with all fields (dealer, seat_profiles, contingents, linked profiles, exclusions). Each test mutates the factory output as needed.

| Test | Verifies |
|---|---|
| `test_rotate_seat_map` | `_rotate_seat` maps W→N, N→E, E→S, S→W; rejects bad input |
| `test_input_dict_not_mutated` | calling `rotate_profile(d)` leaves `d` byte-identical |
| `test_dealer_rotated` | `dealer: "W"` becomes `dealer: "N"` |
| `test_hand_dealing_order_rotated` | `["W","N","E","S"]` → `["N","E","S","W"]` |
| `test_seat_profiles_rekeyed` | keys rotate AND inner `seat` field rotates to match |
| `test_subprofile_partner_contingent_seat_rotated` | `partner_seat` rotated when present |
| `test_subprofile_opponent_contingent_seat_rotated` | `opponent_seat` rotated when present |
| `test_subprofile_exclusions_rotated` | each `subprofile_exclusions[].seat` rotated via `R` |
| `test_linked_profiles_swap_ns_ew` | source `ns_linked_profile` becomes output `ew_linked_profile` and vice versa |
| `test_linked_profile_primary_seat_rotated` | `primary_seat` rotated inside each linked profile |
| `test_linked_profile_one_none_handled` | one populated, one `None` swaps cleanly |
| `test_subprofile_map_unchanged` | `subprofile_map` (index-keyed) byte-identical pre/post |
| `test_legacy_fields_stripped` | `ns_role_mode`, `ew_role_mode`, `ns_bespoke_map`, `ew_bespoke_map` are absent in output |
| `test_unchanged_fields_preserved` | weights, standards, suit ranges, category, author, tag, description, rotate_deals_by_default, is_invariants_safety_profile, schema_version, sort_order byte-identical |
| `test_version_reset_to_0_1` | output `version` is `"0.1"` regardless of source version |
| `test_rotated_from_set` | output `rotated_from` equals source filename (basename only) |
| `test_unknown_keys_passthrough` | arbitrary unknown top-level keys carry over verbatim |
| `test_name_swap_and_separator` | `"X does A and Y does B"` → `"Y does A and X does B"`; same on `&`; both casings handled |
| `test_name_override` | `new_name="X"` replaces `profile_name` and bypasses the swap algorithm |
| `test_name_swap_no_separator_raises` | source `profile_name` without ` and ` / ` & ` raises `ProfileError` |
| `test_already_rotated_input_refused` | source with `rotated_from` set raises `ProfileError` |

### Negative-path / exit-code tests (`tests/test_rotate_profile_cli.py`)

CLI tests use `main(argv: list[str]) -> int` injection (the CLI is implemented as a `main()` function called from the `__name__ == "__main__"` block).

| Test | Verifies |
|---|---|
| `test_cli_success_exit_0_writes_file` | happy path: returns 0, file appears at expected path |
| `test_cli_input_not_found_exit_1` | bad input path → exit 1 |
| `test_cli_bad_json_exit_1` | malformed JSON input → exit 1 |
| `test_cli_validation_failure_exit_2` | crafted bad profile (e.g. mismatched seat/key) → exit 2 |
| `test_cli_output_exists_exit_4` | output already exists, no `--force` → exit 4 |
| `test_cli_force_overwrites` | output exists + `--force` → succeeds and overwrites |
| `test_cli_name_override` | `--name "X"` writes profile with `profile_name == "X"` |
| `test_cli_already_rotated_exit_2` | source with `rotated_from` set → exit 2 |
| `test_cli_bad_name_pattern_exit_2` | source name without separator → exit 2 |

### Integration tests (`tests/test_rotate_profile_integration.py`)

Tests write to `tmp_path`, not to `profiles/`. The four real source profiles are read from `profiles/` but outputs go to `tmp_path` to keep the working tree clean.

| Test | Verifies |
|---|---|
| `test_rotate_validates` | rotated fixture passes `HandProfile.from_dict` + `validate_profile` |
| `test_rotate_each_real_profile` | parametrized over the 4 target profiles in `profiles/`; each rotates and validates (output → tmp_path) |

### Manual verification (post-merge)

- Either via the CLI (one invocation per file) or via Admin → "Rotate a profile", produce a rotated copy of each of the 4 target profiles:
  - `profiles/Opps_Open_3_Weak_2s_and_we_Compete_v1.0.json` → `profiles/We_Open_3_Weak_2s_and_Opps_Compete_v0.1.json`
  - `profiles/Opps_Open_Strong_1NT_and_we_Overcall_Cappeletti_v1.0.json` → `profiles/We_Open_Strong_1NT_and_Opps_Overcall_Cappeletti_v0.1.json`
  - `profiles/Opps_Open_&_Our_TO_Dbl_v0.9.json` → `profiles/We_Open_&_Opps_TO_Dbl_v0.1.json` (note: shell-quote the `&`)
  - `profiles/Opps_Open_&_Our_TO_Dbl_Balancing_v0.9.json` → `profiles/We_Open_&_Opps_TO_Dbl_Balancing_v0.1.json`
- Confirm 4 new JSON files appear in `profiles/` with the expected derived names.
- Launch the app, load each rotated profile, generate deals, eyeball the seat assignments and HCP/shape distributions match expectations.

### Git tracking of rotated outputs

Rotated files written to `profiles/` follow the same convention as hand-authored profiles: tracked in git. There is no `.gitignore` rule for them. (If the team later wants user-only rotations, that becomes a separate decision.)

### Test count target

~22 unit + ~9 CLI + ~2 integration = ~33 tests. Project total stays well under 700.

## Resolved Decisions

All review-surfaced decisions resolved during triage on 2026-04-25:

- **D1 — `tag` field:** carry over verbatim. The tag describes the hand's role; the role rotates with the hand.
- **D2 — default `profile_name`:** algorithmic swap (see "Profile-name swap algorithm"). `--name` overrides; refuse with exit 2 if source name has no ` and ` / ` & ` separator.
- **D3 — `--dry-run`:** out of scope. Delete the file if wrong.
- **D4 — batch mode:** out of scope. One file per invocation.
- **D5 — filename derivation:** filename is derived from the new `profile_name` via project's standard slugification, with version reset to `_v0.1.json`.
- **D6 — `description`:** carry over verbatim. Descriptions describe the convention, not the seat.
- **D7 — menu integration:** add an entry to the existing `admin_menu()` (Admin → "Rotate a profile").
- **D8 — provenance:** add a `rotated_from: "<source filename>"` field to the rotated JSON.
- **D9 — already-rotated input:** refuse with exit 2 if source has `rotated_from` set.
