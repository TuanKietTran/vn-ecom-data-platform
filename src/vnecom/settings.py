"""Single source of runtime config. Everything reads env (or .env) via pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# editable/dev install: repo root is two levels above this file; in images set VNECOM_HOME=/opt/vnecom
REPO_ROOT = Path(os.getenv("VNECOM_HOME") or Path(__file__).resolve().parents[2])
CONFIG_DIR = REPO_ROOT / "config"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # deploy
    vnecom_tier: Literal["lite", "standard", "full"] = "lite"
    vnecom_lake_uri: str = str(REPO_ROOT / "lake")
    vnecom_table_format: Literal["delta", "parquet"] = "delta"
    vnecom_timezone: str = "Asia/Ho_Chi_Minh"
    vnecom_sources: str = "synthetic"

    # http behaviour — all yours to tune
    vnecom_http_user_agent: str = "vnecom-tracker/0.1"
    vnecom_http_rps: float = 0.5  # 0 = no client-side rate limit
    vnecom_http_timeout_s: float = 20.0
    vnecom_respect_robots: bool = True  # public/web sources check robots.txt unless this is false
    vnecom_public_max_pages: int = 5  # pages per keyword/category for search-style sources

    # Shopee Affiliate Open API (market-wide offers) — https://affiliate.shopee.vn
    shopee_affiliate_app_id: str | None = None
    shopee_affiliate_secret: SecretStr | None = None
    shopee_affiliate_host: str = "https://open-api.affiliate.shopee.vn/graphql"
    shopee_affiliate_keywords: str = (
        "điện thoại,laptop,tai nghe,nồi chiên không dầu,kem chống nắng,sữa rửa mặt,tã,sữa bột"
    )

    # AccessTrade VN publisher datafeeds (Shopee/Lazada/Tiki/… product feeds) — https://pub.accesstrade.vn
    accesstrade_token: SecretStr | None = None
    accesstrade_host: str = "https://api.accesstrade.vn/v1"
    accesstrade_domains: str = "shopee.vn,lazada.vn,tiki.vn"
    accesstrade_page_size: int = 200

    # public web search sources
    lazada_public_keywords: str = "điện thoại,laptop,tai nghe bluetooth,nồi chiên không dầu,kem chống nắng"
    sendo_public_keywords: str = "áo thun,giày thể thao,nồi cơm điện,ốp lưng"

    # first-party retailers via schema.org JSON-LD (see config/retailers.yaml)
    retail_retailers: str = "thegioididong,dienmayxanh,bachhoaxanh,fptshop,cellphones,hasaki,fahasa"
    retail_max_products: int = 300  # per retailer per run; stable sample so the same SKUs are tracked daily

    # tiki
    tiki_category_ids: str = "1789,1815,8322"

    # shopee open platform
    shopee_partner_id: int | None = None
    shopee_partner_key: SecretStr | None = None
    shopee_shop_id: int | None = None
    shopee_access_token: SecretStr | None = None
    shopee_host: str = "https://partner.shopeemobile.com"

    # lazada open platform (VN gateway)
    lazada_app_key: str | None = None
    lazada_app_secret: SecretStr | None = None
    lazada_access_token: SecretStr | None = None
    lazada_host: str = "https://api.lazada.vn/rest"

    # tiktok shop
    tiktok_app_key: str | None = None
    tiktok_app_secret: SecretStr | None = None
    tiktok_access_token: SecretStr | None = None
    tiktok_shop_cipher: str | None = None
    tiktok_host: str = "https://open-api.tiktokglobalshop.com"

    # licensed feed
    feed_vendor: str | None = None

    # s3 / minio
    aws_access_key_id: str | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_endpoint_url: str | None = None
    aws_region: str = "us-east-1"

    # spark
    spark_master: str = "local[*]"
    spark_driver_memory: str = "2g"

    # synthetic generator knobs
    synthetic_products_per_platform: int = Field(default=400, ge=10)
    synthetic_seed: int = 42

    @property
    def sources(self) -> list[str]:
        return [s.strip() for s in self.vnecom_sources.split(",") if s.strip()]

    @property
    def is_remote_lake(self) -> bool:
        return self.vnecom_lake_uri.startswith(("s3://", "s3a://"))

    def lake_path(self, *parts: str, for_spark: bool = False) -> str:
        """Path inside the lake. Spark wants s3a://, fsspec/deltalake want s3://."""
        base = self.vnecom_lake_uri.rstrip("/")
        if self.is_remote_lake:
            scheme_free = base.split("://", 1)[1]
            base = f"{'s3a' if for_spark else 's3'}://{scheme_free}"
        else:
            base = str(Path(base).resolve())
        return "/".join([base, *parts])

    def storage_options(self) -> dict[str, str]:
        """fsspec / deltalake storage options for MinIO."""
        if not self.is_remote_lake:
            return {}
        opts = {
            "key": self.aws_access_key_id or "",
            "secret": self.aws_secret_access_key.get_secret_value() if self.aws_secret_access_key else "",
        }
        if self.aws_endpoint_url:
            opts["client_kwargs"] = {"endpoint_url": self.aws_endpoint_url}  # type: ignore[assignment]
        return opts


@lru_cache
def get_settings() -> Settings:
    return Settings()
