"""Produce a finite batch, consume it through the Spark consumer, and assert bronze writes."""

from __future__ import annotations

import argparse
import re
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = [
    "docker",
    "compose",
    "--env-file",
    ".env",
    "-f",
    "docker/compose.yml",
    "--profile",
    "core",
    "--profile",
    "full",
]


def run(command: list[str]) -> str:
    result = subprocess.run(command, cwd=ROOT, check=True, text=True, capture_output=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")
    return result.stdout


def assert_counts(output: str, expected: int) -> None:
    match = re.search(r"Kafka events consumed: (\d+); new bronze rows: (\d+)", output)
    if match is None or tuple(map(int, match.groups())) != (expected, expected):
        raise RuntimeError(f"consumer did not verify exactly {expected} Kafka and bronze rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100)
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count must be positive")

    topic = f"vnecom.verify.{uuid.uuid4().hex}"
    run(
        COMPOSE
        + [
            "run",
            "--rm",
            "--no-deps",
            "price-producer",
            "python",
            "-m",
            "vnecom.stream.producer",
            "--bootstrap",
            "redpanda:9092",
            "--topic",
            topic,
            "--count",
            str(args.count),
        ]
    )
    output = run(
        COMPOSE
        + [
            "run",
            "--rm",
            "--no-deps",
            "price-stream",
            "python",
            "-m",
            "vnecom.spark.stream_prices",
            "--bootstrap",
            "redpanda:9092",
            "--topic",
            topic,
            "--expected-count",
            str(args.count),
        ]
    )
    assert_counts(output, args.count)
    print(f"PASS: {args.count} events delivered to Redpanda and appended to bronze/price_events")


if __name__ == "__main__":
    main()
