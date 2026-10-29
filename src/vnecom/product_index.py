"""Incremental, provenance-preserving local product search with retained price history."""

import hashlib
import json
import os
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from vnecom.settings import REPO_ROOT, Settings
from vnecom.text.vn import normalize_title


class ProductIndex:
    def __init__(self, path: Path | None = None):
        warehouse = Path(os.getenv("VNECOM_WAREHOUSE", str(REPO_ROOT / "warehouse" / "vnecom.duckdb")))
        self.path = path or warehouse.with_name("products.sqlite")

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY, source TEXT, platform TEXT, title_norm TEXT,
                observed_at TEXT, active INTEGER, content_hash TEXT, payload TEXT
            );
            CREATE TABLE IF NOT EXISTS prices (
                id TEXT, observed_at TEXT, price_vnd INTEGER,
                PRIMARY KEY(id, observed_at)
            );
            CREATE TABLE IF NOT EXISTS watermarks (
                source TEXT, platform TEXT, observed_at TEXT, PRIMARY KEY(source, platform)
            );
        """)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def sync(self, rows: list[dict], *, complete_snapshot: bool) -> dict[str, int]:
        if not complete_snapshot:
            raise ValueError("Incomplete snapshots must not retire indexed products")
        groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for row in rows:
            if not row.get("product_id") or not row.get("source") or not row.get("platform"):
                raise ValueError("Product indexing requires source/platform/product identity")
            groups[(row["source"], row["platform"])].append(row)
        stats = {"inserted": 0, "updated": 0, "unchanged": 0, "retired": 0, "older_snapshots_skipped": 0}
        with self._connect() as connection:
            for (source, platform), group in groups.items():
                snapshot = max(_timestamp(row["captured_at"]) for row in group)
                watermark = connection.execute(
                    "SELECT observed_at FROM watermarks WHERE source=? AND platform=?", (source, platform)
                ).fetchone()
                if watermark and watermark[0] > snapshot:
                    stats["older_snapshots_skipped"] += 1
                    continue
                seen = []
                for raw in group:
                    row = dict(raw)
                    for transient in ("run_id", "_silver_loaded_at", "_bronze_file"):
                        row.pop(transient, None)
                    observed = _timestamp(row["captured_at"])
                    identity = ":".join(
                        [source, platform, str(row["product_id"]), str(row.get("sku_id") or "")]
                    )
                    seen.append(identity)
                    row["captured_at"] = observed
                    row["price_vnd"] = row.get("price_vnd", row.get("price_close_vnd"))
                    if row["price_vnd"] is None or int(row["price_vnd"]) <= 0:
                        raise ValueError("Indexed products require a positive known price")
                    prior_price = connection.execute(
                        "SELECT price_vnd FROM prices WHERE id=? AND observed_at=?", (identity, observed)
                    ).fetchone()
                    if prior_price and prior_price[0] != int(row["price_vnd"]):
                        raise ValueError(
                            "Conflicting prices for the same observation; supply a new observation timestamp"
                        )
                    encoded = json.dumps(row, sort_keys=True, default=str, ensure_ascii=False)
                    digest = hashlib.sha256(encoded.encode()).hexdigest()
                    old = connection.execute(
                        "SELECT observed_at,content_hash FROM products WHERE id=?", (identity,)
                    ).fetchone()
                    if old and old[0] > observed:
                        continue
                    if old and old[1] == digest:
                        stats["unchanged"] += 1
                    else:
                        stats["updated" if old else "inserted"] += 1
                    connection.execute(
                        """
                        INSERT INTO products VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                        title_norm=excluded.title_norm, observed_at=excluded.observed_at,
                        active=excluded.active, content_hash=excluded.content_hash, payload=excluded.payload
                    """,
                        (
                            identity,
                            source,
                            platform,
                            normalize_title(row.get("title") or ""),
                            observed,
                            row.get("in_stock") is not False,
                            digest,
                            encoded,
                        ),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO prices VALUES(?,?,?)",
                        (identity, observed, int(row["price_vnd"])),
                    )
                active = connection.execute(
                    "SELECT id FROM products WHERE source=? AND platform=? AND active=1", (source, platform)
                ).fetchall()
                for product in active:
                    if product[0] not in seen:
                        connection.execute("UPDATE products SET active=0 WHERE id=?", (product[0],))
                        stats["retired"] += 1
                connection.execute(
                    "INSERT OR REPLACE INTO watermarks VALUES(?,?,?)", (source, platform, snapshot)
                )
        return stats

    def search(
        self, query: str, *, include_synthetic: bool = False, now: datetime | None = None, limit: int = 10
    ) -> list[dict]:
        if not self.path.exists():
            return []
        now = now or datetime.now(UTC)
        tokens = (normalize_title(query) or "").split()
        if not tokens:
            return []
        with self._connect() as connection:
            sql = "SELECT id,payload FROM products WHERE active=1 AND observed_at>=? AND observed_at<=?"
            args = [(now - timedelta(hours=24)).isoformat(), now.isoformat()]
            for token in tokens[:20]:
                sql += " AND instr(title_norm, ?) > 0"
                args.append(token)
            sql += " ORDER BY observed_at DESC LIMIT 200"
            results = []
            for row in connection.execute(sql, args):
                value = json.loads(row["payload"])
                if not include_synthetic and value.get("source_tier") == "synthetic":
                    continue
                value["index_id"] = row["id"]
                history = connection.execute(
                    "SELECT observed_at,price_vnd FROM prices WHERE id=? AND observed_at>=? ORDER BY observed_at",
                    (row["id"], (now - timedelta(days=30)).isoformat()),
                ).fetchall()
                value["price_history"] = [dict(item) for item in history]
                results.append(value)
        return sorted(results, key=lambda row: row["price_vnd"])[:limit]


def _timestamp(value) -> str:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)  # Spark timestamps are UTC in the configured session.
    return parsed.astimezone(UTC).isoformat()


def sync_lake(settings: Settings, index: ProductIndex | None = None) -> dict[str, int]:
    import duckdb

    from vnecom.pipeline import assert_publishable

    assert_publishable(settings)
    if settings.is_remote_lake or settings.vnecom_table_format != "parquet":
        raise ValueError("Local product indexing currently requires a Parquet lake")
    path = settings.lake_path("silver", "product_daily", "**", "*.parquet")
    with duckdb.connect(":memory:") as connection:
        result = connection.execute(
            """
            SELECT * EXCLUDE(latest_date) FROM (
                SELECT *, max(capture_date) OVER(PARTITION BY source, platform) latest_date
                FROM read_parquet(?, hive_partitioning=true) WHERE captured_at <= ?::TIMESTAMP
            ) WHERE capture_date=latest_date
        """,
            [path, datetime.now(UTC).replace(tzinfo=None)],
        )
        columns = [c[0] for c in result.description]
        rows = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    return (index or ProductIndex()).sync(rows, complete_snapshot=True)
