from bridge_engine.deal_generator import classify_viability


def test_viability_unknown_when_no_attempts() -> None:
    assert classify_viability(successes=0, attempts=0) == "unknown"
    assert classify_viability(successes=0, attempts=-5) == "unknown"


def test_viability_unknown_when_too_few_zero_success_attempts() -> None:
    # Fewer than 10 attempts and no successes -> still "unknown"
    assert classify_viability(successes=0, attempts=1) == "unknown"
    assert classify_viability(successes=0, attempts=9) == "unknown"


def test_viability_unviable_when_many_attempts_and_zero_successes() -> None:
    # 10+ attempts, no successes -> unviable
    assert classify_viability(successes=0, attempts=10) == "unviable"
    assert classify_viability(successes=0, attempts=50) == "unviable"


def test_viability_unlikely_when_rare_successes() -> None:
    # Some successes, but success_rate < 0.1 -> unlikely
    # 1 / 20 = 0.05
    assert classify_viability(successes=1, attempts=20) == "unlikely"
    # 2 / 30 ≈ 0.066
    assert classify_viability(successes=2, attempts=30) == "unlikely"


def test_viability_likely_when_success_rate_reasonable() -> None:
    # success_rate >= 0.1 -> likely
    assert classify_viability(successes=1, attempts=5) == "likely"  # 0.2
    assert classify_viability(successes=2, attempts=10) == "likely"  # 0.2
    assert classify_viability(successes=9, attempts=10) == "likely"  # 0.9
