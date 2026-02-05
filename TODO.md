# TODOs

## Start Tasks
- [ ] Run profile management in program

---

## Architecture

### 1. [ ] Constructive Help for Nonstandard Seats
| # | Item | Description |
|---|------|-------------|
| 1a | v1 gates | Empty minima extraction blocks RS/PC/OC |
| 1b | NS role filtering | Honor driver_only/follower_only |
| 1c | Driver/follower | Which NS seat leads |
| 1d | RS reordering | Try suits by past success |
| 1e | Smart deal order | Step 2: reorder for RS/driver/PC/OC |

### 2. [ ] V2 Policy Validation
| # | Item | Description |
|---|------|-------------|
| 2a | PC/OC nudging | Try alternate subprofiles on failure |
| 2b | Integration tests | Prove v2 policy improves success |

---

## Enhancements
3. [ ] Metrics export CLI - `export-metrics <profile> [--boards N]`

---

## Summary
| Category | Count |
|----------|-------|
| Architecture | 2 |
| Enhancements | 1 |
| **Total** | **3** |

**Tests**: 240 passed, 4 skipped | **Branch**: refactor/deal-generator

---

## Completed (31 items)
<details>
<summary>Click to expand</summary>

- Magic profile name checks, constraint state to v2, "too hard = unviable" rule
- Subprofile viability tracking, HCP vs shape classification, attribution to policy
- Standard vs nonstandard analysis, default dealing order (Steps 1,3,4,5)
- Latent bugs (3), dead code (10), performance (1), code quality (6), future (3)

</details>
