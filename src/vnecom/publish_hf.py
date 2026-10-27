"""Publish a deliberately small, redacted product dataset to the Hub."""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

import yaml

ALLOWLIST = (
    "source", "platform", "platform_kind", "title", "title_norm", "brand", "category_code",
    "capture_date", "price_close_vnd", "price_min_vnd", "price_max_vnd", "price_avg_vnd",
    "list_price_vnd", "discount_pct_displayed", "sold_count", "sold_count_is_bucketed",
    "units_est", "units_basis", "gmv_est_vnd", "had_stockout", "rating_avg", "review_count",
)
PII_PATTERNS = (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), re.compile(r"(?:\+?84|0)\d{9,10}"))
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "hf_publish.yaml"


def redact(value):
    if not isinstance(value, str):
        return value
    for pattern in PII_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value


def allowed_sources(config_path: Path = CONFIG_PATH) -> set[str]:
    config = yaml.safe_load(config_path.read_text()) or {}
    sources = config.get("allowed_sources")
    if not isinstance(sources, list) or not all(isinstance(item, str) for item in sources):
        raise ValueError("hf_publish.yaml must define allowed_sources as a list")
    return set(sources)


def build_dataset(warehouse: str | Path):
    import duckdb

    con = duckdb.connect(str(warehouse), read_only=True)
    try:
        table = con.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'fct_listing_daily' ORDER BY CASE WHEN table_schema = 'gold' THEN 0 ELSE 1 END LIMIT 1").fetchone()
        if table is None:
            raise ValueError("warehouse lacks gold.fct_listing_daily")
        relation = '"' + table[0].replace('"', '""') + '"."fct_listing_daily"'
        available = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()}
        if "source" not in available:
            raise ValueError("fct_listing_daily lacks required source field")
        permitted = allowed_sources()
        source_rows = con.execute(f'SELECT DISTINCT "source" FROM {relation}').fetchall()
        if any(row[0] is None for row in source_rows):
            raise ValueError("warehouse contains missing source values")
        present = {row[0] for row in source_rows}
        rejected = present - permitted
        if rejected:
            raise ValueError(f"disallowed source(s) in warehouse: {', '.join(sorted(rejected))}")
        columns = [name for name in ALLOWLIST if name in available]
        if not columns:
            raise ValueError("fct_listing_daily has no allowlisted columns")
        frame = con.execute("SELECT " + ", ".join('"' + c + '"' for c in columns) + f" FROM {relation}").df()
    finally:
        con.close()
    for column in frame.select_dtypes(include="object"):
        frame[column] = frame[column].map(redact)
    return frame


def export_parquet(frame, output_dir: str | Path) -> int:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "products.parquet"
    frame.to_parquet(path, index=False)
    return path.stat().st_size


def publish(warehouse: str | Path, repo_id: str, *, output_dir: str | Path = "hf_export", private: bool = True,
            dry_run: bool = False, yes: bool = False) -> int:
    if not dry_run and (not yes or not os.environ.get("HF_TOKEN")):
        raise ValueError("upload requires --yes and HF_TOKEN")
    frame = build_dataset(warehouse)
    size = export_parquet(frame, output_dir)
    counts = {str(source): int(count) for source, count in frame.groupby("source", dropna=False).size().items()}
    if dry_run:
        return len(frame), counts, size
    token = os.environ["HF_TOKEN"]
    from datasets import Dataset
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)
    dates = frame["capture_date"].dropna().astype(str) if "capture_date" in frame else []
    date_min, date_max = (min(dates), max(dates)) if len(dates) else ("unknown", "unknown")
    schema = {str(column): str(dtype) for column, dtype in frame.dtypes.items()}
    card = ("---\npretty_name: Vietnamese E-commerce Product Listings\n"
            'task_categories:\n  - tabular-regression\nlicense: other\nlicense_note: "Third-party record license not asserted; check source terms."\n'
            f"sources: {json.dumps(sorted(counts))}\ncollection_date_min: {json.dumps(date_min)}\ncollection_date_max: {json.dumps(date_max)}\n"
            f"schema: {json.dumps(schema, sort_keys=True)}\nsource_row_counts: {json.dumps(counts, sort_keys=True)}\n---\n\n"
            "# Vietnamese E-commerce Product Listings\n\n"
            "Product-level listing and price observations from the named sources; identifiers and seller details are excluded and contact-like strings redacted.\n\n"
            "## License and use caveats\n\n"
            "The license of the collected third-party data is unknown; no license is granted for those records. Users must verify applicable source terms and rights. Collection may be subject to source terms of service and robots.txt policies. This project is not affiliated with the named platforms.\n")
    api.upload_file(path_or_fileobj=io.BytesIO(card.encode()), path_in_repo="README.md", repo_id=repo_id, repo_type="dataset")
    Dataset.from_pandas(frame, preserve_index=False).push_to_hub(repo_id, private=private, token=token)
    return len(frame)
