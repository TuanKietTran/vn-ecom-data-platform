"""Real end-user smoke test with isolated supplied synthetic fixtures and owned service lifecycle."""

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


def configured_port(name: str, default: int) -> int:
    value = int(os.environ.get(name, default))
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be from 1 through 65535")
    return value


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    api_port = configured_port("CLIENT_API_PORT", 8201)
    gateway_port = configured_port("CLIENT_GATEWAY_PORT", 3202)
    web_port = configured_port("CLIENT_WEB_PORT", 3201)
    if len({api_port, gateway_port, web_port}) != 3:
        raise ValueError("CLIENT_API_PORT, CLIENT_GATEWAY_PORT, and CLIENT_WEB_PORT must be distinct")
    for port in (api_port, gateway_port, web_port):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                raise RuntimeError(f"Port {port} is occupied; stop your own service before the isolated test")
        except OSError:
            pass

    with tempfile.TemporaryDirectory(prefix="hunt-clients-") as temporary:
        state = Path(temporary)
        artifacts = Path(os.environ.get("CLIENT_ARTIFACT_DIR", state / "artifacts"))
        artifacts.mkdir(parents=True, exist_ok=True)
        logs_dir = state / "logs"
        logs_dir.mkdir()
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
        api_url = f"http://127.0.0.1:{api_port}"
        gateway_url = f"http://127.0.0.1:{gateway_port}"
        web_url = f"http://127.0.0.1:{web_port}"
        environment = {
            **os.environ,
            "VNECOM_LAKE_URI": str(state / "lake"),
            "VNECOM_WAREHOUSE": str(warehouse),
            "VNECOM_SOURCES": "synthetic",
            "VNECOM_AI_ENABLED": "false",
            "VNECOM_TABLE_FORMAT": "parquet",
            "NEXT_TELEMETRY_DISABLED": "1",
            "PLATFORM_API_URL": api_url,
            "GATEWAY_PORT": str(gateway_port),
            "CLIENT_GATEWAY_URL": gateway_url,
            "CLIENT_API_PORT": str(api_port),
            "CLIENT_GATEWAY_PORT": str(gateway_port),
            "CLIENT_WEB_PORT": str(web_port),
            "CLIENT_WEB_URL": web_url,
            "CLIENT_ARTIFACT_DIR": str(artifacts),
        }
        npm = "npm.cmd" if os.name == "nt" else "npm"
        subprocess.run([npm, "run", "build"], cwd=ROOT, env=environment, check=True, timeout=300)
        vnecom = ROOT / ".venv" / ("Scripts/vnecom.exe" if os.name == "nt" else "bin/vnecom")
        processes: list[subprocess.Popen] = []
        logs = []
        services = [
            ([str(vnecom), "ai", "serve", "--host", "127.0.0.1", "--port", str(api_port)], ROOT, f"{api_url}/health", "platform"),
            (["node", "dist/main.js"], ROOT / "apps/gateway", f"{gateway_url}/health", "gateway"),
            (["node", "../../node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", str(web_port)], ROOT / "apps/web", web_url, "web"),
        ]
        try:
            for command, cwd, health_url, name in services:
                log = (logs_dir / f"{name}.log").open("w", encoding="utf-8")
                logs.append(log)
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    env=environment,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=os.name != "nt",
                )
                processes.append(process)
                print(f"STARTED {name} pid={process.pid}", flush=True)
                for _ in range(100):
                    if process.poll() is not None:
                        log.flush()
                        raise RuntimeError(f"{name} exited; inspect {logs_dir / (name + '.log')}")
                    try:
                        urllib.request.urlopen(health_url, timeout=1).close()
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError(f"{name} readiness timed out at {health_url}")
            subprocess.run(
                ["node", "apps/web/tests/end-user.cjs"], cwd=ROOT, env=environment, check=True, timeout=180
            )
        finally:
            for process in reversed(processes):
                stop_process(process)
                print(f"STOPPED {process.pid}", flush=True)
            for log in logs:
                log.close()


if __name__ == "__main__":
    main()
