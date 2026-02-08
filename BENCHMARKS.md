# Benchmark Tests

This document describes the opt-in benchmark tests for profiling deal generation performance.

## Available Benchmarks

All benchmarks are skipped by default to keep the regular test suite fast. Enable them via environment variables.

### 1. Constructive Help Benchmark (All Standard Profiles)

Tests constructive help algorithm (v1 on vs off) across 5 standard profiles.

```bash
RUN_CONSTRUCTIVE_BENCHMARKS=1 pytest -q -s tests/test_constructive_benchmark_std_profiles.py
```

**What it tests:**
- 5 standard profiles × 120 boards × 2 seeds × 2 modes = 480 total boards
- MAX_ATTEMPTS = 500
- Compares success rates with constructive help ON vs OFF

**Expected runtime:** ~30-60 seconds

---

### 2. Profile E Rotation Rank Benchmark

Tests rotation and helper-seat ranking for Profile E (the most constrained profile).

```bash
RUN_PROFILE_E_ROTATION_RANK=1 pytest -q -s tests/test_profile_e_rotation_rank_helper_seat.py
```

**What it tests:**
- 4 rotation runs × 50 boards per run = 200 boards
- MAX_ATTEMPTS = 500
- Seat-level failure attribution across rotated dealing orders
- Helper-seat selection based on pain-share thresholds

**Expected runtime:** ~20-40 seconds

---

### 3. Profile E Failure Attribution Benchmark

Tests failure attribution data collection for Profile E.

```bash
RUN_PROFILE_E_ATTRIBUTION=1 pytest -q -s tests/test_profile_e_failure_attribution.py
```

**What it tests:**
- 200 boards sampled
- Per-seat failure attribution (HCP, shape, seat viability)
- Accumulates attribution across all attempts

**Expected runtime:** ~10-30 seconds

---

## Running All Benchmarks

To run all benchmarks at once:

```bash
RUN_CONSTRUCTIVE_BENCHMARKS=1 \
RUN_PROFILE_E_ROTATION_RANK=1 \
RUN_PROFILE_E_ATTRIBUTION=1 \
pytest -v -s tests/test_*benchmark*.py tests/test_profile_e_*.py
```

Or as a single line:

```bash
RUN_CONSTRUCTIVE_BENCHMARKS=1 RUN_PROFILE_E_ROTATION_RANK=1 RUN_PROFILE_E_ATTRIBUTION=1 pytest -v -s tests/test_*benchmark*.py tests/test_profile_e_*.py
```

---

## Pytest Markers

Benchmarks use the `@pytest.mark.slow` marker defined in `pytest.ini`:

```ini
markers =
    slow: slow/benchmark tests (opt-in or longer-running)
```

To list all tests with the slow marker:

```bash
pytest --collect-only -m slow
```

---

## Adding New Benchmarks

When adding new benchmarks:

1. Add an environment variable gate at the top of the test file:
   ```python
   if os.environ.get("RUN_MY_BENCHMARK", "") != "1":
       pytest.skip("Opt-in benchmark...", allow_module_level=True)
   ```

2. Add the `@pytest.mark.slow` marker to the test function

3. Document the benchmark in this file

---

## Debug Hooks for Instrumentation

Benchmarks use debug hooks in `deal_generator.py` for telemetry:

| Hook | Purpose |
|------|---------|
| `_DEBUG_STANDARD_CONSTRUCTIVE_USED` | Track when v1 constructive help is applied |
| `_DEBUG_ON_ATTEMPT_FAILURE_ATTRIBUTION` | Per-attempt failure attribution |
| `_DEBUG_ON_MAX_ATTEMPTS` | When MAX_BOARD_ATTEMPTS is exhausted |
