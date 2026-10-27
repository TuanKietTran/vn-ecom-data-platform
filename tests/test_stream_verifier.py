import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "verify_redpanda_stream", Path(__file__).parents[1] / "scripts" / "verify_redpanda_stream.py"
)
_verifier = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(_verifier)
assert_counts = _verifier.assert_counts


def test_verifier_requires_exact_kafka_and_bronze_counts():
    assert_counts("Kafka events consumed: 5; new bronze rows: 5", 5)


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("Kafka events consumed: 4; new bronze rows: 5", 5),
        ("Kafka events consumed: 5; new bronze rows: 4", 5),
        ("no count report", 5),
    ],
)
def test_verifier_rejects_mismatched_counts(output, expected):
    with pytest.raises(RuntimeError, match="did not verify exactly"):
        assert_counts(output, expected)
