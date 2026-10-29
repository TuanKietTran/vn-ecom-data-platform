"""Real end-user smoke test with an owned service lifecycle and isolated synthetic fixtures."""

import os
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from vnecom.deal_catalog import demo_catalog, save_catalog
from vnecom.product_index import ProductIndex
from vnecom.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts" / "clients"


def main() -> None:
    for port in (8000, 4100, 3001):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                raise RuntimeError(f"Port {port} is occupied; stop your own service before the isolated test")
        except OSError:
            pass
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="shoplens-clients-") as temporary:
        state = Path(temporary)
        warehouse = state / "platform.duckdb"
        settings = Settings(vnecom_lake_uri=str(state / "lake"), vnecom_sources="synthetic")
        save_catalog(settings, demo_catalog())
        day = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date() - timedelta(days=1)
        with duckdb.connect(str(warehouse)) as connection:
            connection.execute("CREATE SCHEMA gold")
            connection.execute(
                """CREATE TABLE gold.mart_platform_source_daily AS
                SELECT ?::DATE capture_date, 'tiki' platform, 'synthetic' source, 'synthetic' source_tier,
                       20 listings_tracked, 3 sellers_tracked, 10 units_est, 123000 gmv_est_vnd,
                       12300 avg_price_vnd, 1.0 gmv_share""",
                [day],
            )
        ProductIndex(state / "products.sqlite").sync(
            [
                {
                    "product_id": "client-fixture",
                    "sku_id": "128",
                    "title": "Điện thoại Apple Test 128GB",
                    "platform": "tiki",
                    "source": "synthetic",
                    "source_tier": "synthetic",
                    "captured_at": datetime.now(UTC).isoformat(),
                    "price_vnd": 5_000_000,
                    "in_stock": True,
                }
            ],
            complete_snapshot=True,
        )
        environment = {
            **os.environ,
            "VNECOM_LAKE_URI": str(state / "lake"),
            "VNECOM_WAREHOUSE": str(warehouse),
            "VNECOM_SOURCES": "synthetic",
            "VNECOM_AI_ENABLED": "false",
            "VNECOM_TABLE_FORMAT": "parquet",
            "NEXT_TELEMETRY_DISABLED": "1",
            "PLATFORM_API_URL": "http://127.0.0.1:8000",
            "CLIENT_ARTIFACT_DIR": str(ARTIFACTS),
        }
        processes, logs = [], []
        try:
            for command, cwd, url, name in [
                (
                    [str(ROOT / ".venv/bin/vnecom"), "ai", "serve", "--host", "127.0.0.1", "--port", "8000"],
                    ROOT,
                    "http://127.0.0.1:8000/health",
                    "platform",
                ),
                (["node", "dist/main.js"], ROOT / "apps/gateway", "http://127.0.0.1:4100/health", "gateway"),
                (
                    [
                        "node",
                        "../../node_modules/next/dist/bin/next",
                        "start",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        "3001",
                    ],
                    ROOT / "apps/web",
                    "http://127.0.0.1:3001",
                    "web",
                ),
            ]:
                log = (ARTIFACTS / f"{name}.log").open("w")
                logs.append(log)
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                processes.append(process)
                for _ in range(100):
                    if process.poll() is not None:
                        raise RuntimeError(f"{name} exited; inspect {name}.log. Use unoccupied test ports.")
                    try:
                        urllib.request.urlopen(url, timeout=1).close()
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError(f"{name} readiness timed out")
            subprocess.run(
                ["node", "apps/web/tests/end-user.cjs"], cwd=ROOT, env=environment, check=True, timeout=150
            )
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
            for log in logs:
                log.close()


if __name__ == "__main__":
    main()
