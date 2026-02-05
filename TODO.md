# TODOs

## Start Tasks
- [ ] Run profile management in program

---

## Architecture

### 1. [ ] Smart Deal Order
| # | Item | Description |
|---|------|-------------|
| 1a | ~~Smart deal order~~ | ✅ `_smart_dealing_order()` in wizard_flow.py |
| 1a-i | NS random driver | How does `random_driver` interact at runtime? |
| 1b | NS role filtering | Honor driver_only/follower_only |
| 1c | Driver/follower | Which NS seat leads |

### 2. [ ] Constructive Help for Nonstandard Seats
| # | Item | Description |
|---|------|-------------|
| 2a | PC/OC nudging | Try alternate subprofiles on failure |
| 2b | RS reordering | Try suits by past success |
| 2c | v1 gates | Empty minima extraction blocks RS/PC/OC |

### 3. [ ] V2 Policy Validation
| # | Item | Description |
|---|------|-------------|
| 3a | Integration tests | Prove v2 policy improves success |

---

## Enhancements
4. [ ] Metrics export CLI - `export-metrics <profile> [--boards N]`

---

## Summary
| Category | Count |
|----------|-------|
| Architecture | 3 |
| Enhancements | 1 |
| **Total** | **4** |

**Tests**: 268 passed, 4 skipped | **Branch**: refactor/deal-generator

---

## Completed (31 items)
<details>
<summary>Click to expand</summary>

- Magic profile name checks, constraint state to v2, "too hard = unviable" rule
- Subprofile viability tracking, HCP vs shape classification, attribution to policy
- Standard vs nonstandard analysis, default dealing order (Steps 1,3,4,5)
- Latent bugs (3), dead code (10), performance (1), code quality (6), future (3)

</details>
