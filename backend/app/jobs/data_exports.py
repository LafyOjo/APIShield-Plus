from __future__ import annotations

import argparse
import csv
import gzip
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exports import DEFAULT_EXPORT_DATASETS, validate_export_datasets
from app.core.metrics import record_job_run
from app.core.time import utcnow
from app.models.data_exports import DataExportConfig, DataExportRun
from app.models.tenants import Tenant
from app.models.geo_event_aggs import GeoEventAgg
from app.models.incidents import Incident
from app.models.notification_deliveries import NotificationDelivery
from app.models.revenue_impact import ConversionMetric
from app.models.security_events import SecurityEvent


logger = logging.getLogger(__name__)

DATASET_SCHEMAS: dict[str, list[str]] = {
    "incidents": [
        "id",
        "tenant_id",
        "website_id",
        "environment_id",
        "status",
        "category",
        "title",
        "severity",
        "first_seen_at",
        "last_seen_at",
        "primary_ip_hash",
        "primary_country_code",
        "impact_estimate_id",
        "assigned_to_user_id",
        "created_at",
        "updated_at",
    ],
    "security_events": [
        "id",
        "tenant_id",
        "website_id",
        "environment_id",
        "user_id",
        "created_at",
        "event_ts",
        "category",
        "event_type",
        "severity",
        "source",
        "request_path",
        "method",
        "status_code",
        "user_identifier",
        "session_id",
        "user_agent",
        "ip_hash",
        "country_code",
        "region",
        "city",
        "latitude",
        "longitude",
        "asn_number",
        "asn_org",
        "is_datacenter",
        "meta",
    ],
    "geo_agg": [
        "id",
        "tenant_id",
        "website_id",
        "environment_id",
        "bucket_start",
        "event_category",
        "severity",
        "country_code",
        "region",
        "city",
        "latitude",
        "longitude",
        "asn_number",
        "asn_org",
        "is_datacenter",
        "count",
    ],
    "conversion_metrics": [
        "id",
        "tenant_id",
        "website_id",
        "environment_id",
        "metric_key",
        "window_start",
        "window_end",
        "sessions",
        "conversions",
        "conversion_rate",
        "revenue_per_conversion",
        "captured_at",
    ],
    "notification_deliveries": [
        "id",
        "tenant_id",
        "rule_id",
        "channel_id",
        "status",
        "created_at",
        "sent_at",
        "dedupe_key",
        "payload_json",
        "error_message",
        "attempt_count",
    ],
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).isoformat()
    return value.isoformat()


def _serialize_json(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def _export_incidents(
    db: Session, *, tenant_id: int, start: datetime, end: datetime
) -> Iterable[dict]:
    query = (
        db.query(Incident)
        .filter(
            Incident.tenant_id == tenant_id,
            Incident.created_at >= start,
            Incident.created_at < end,
        )
        .order_by(Incident.id.asc())
    )
    for row in query.yield_per(1000):
        yield {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "website_id": row.website_id,
            "environment_id": row.environment_id,
            "status": row.status,
            "category": row.category,
            "title": row.title,
            "severity": row.severity,
            "first_seen_at": _iso(row.first_seen_at),
            "last_seen_at": _iso(row.last_seen_at),
            "primary_ip_hash": row.primary_ip_hash,
            "primary_country_code": row.primary_country_code,
            "impact_estimate_id": row.impact_estimate_id,
            "assigned_to_user_id": row.assigned_to_user_id,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }


def _export_security_events(
    db: Session, *, tenant_id: int, start: datetime, end: datetime
) -> Iterable[dict]:
    query = (
        db.query(SecurityEvent)
        .filter(
            SecurityEvent.tenant_id == tenant_id,
            SecurityEvent.created_at >= start,
            SecurityEvent.created_at < end,
        )
        .order_by(SecurityEvent.id.asc())
    )
    for row in query.yield_per(1000):
        yield {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "website_id": row.website_id,
            "environment_id": row.environment_id,
            "user_id": row.user_id,
            "created_at": _iso(row.created_at),
            "event_ts": _iso(row.event_ts),
            "category": row.category,
            "event_type": row.event_type,
            "severity": row.severity,
            "source": row.source,
            "request_path": row.request_path,
            "method": row.method,
            "status_code": row.status_code,
            "user_identifier": row.user_identifier,
            "session_id": row.session_id,
            "user_agent": row.user_agent,
            "ip_hash": row.ip_hash,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "asn_number": row.asn_number,
            "asn_org": row.asn_org,
            "is_datacenter": row.is_datacenter,
            "meta": row.meta,
        }


def _export_geo_agg(
    db: Session, *, tenant_id: int, start: datetime, end: datetime
) -> Iterable[dict]:
    query = (
        db.query(GeoEventAgg)
        .filter(
            GeoEventAgg.tenant_id == tenant_id,
            GeoEventAgg.bucket_start >= start,
            GeoEventAgg.bucket_start < end,
        )
        .order_by(GeoEventAgg.id.asc())
    )
    for row in query.yield_per(1000):
        yield {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "website_id": row.website_id,
            "environment_id": row.environment_id,
            "bucket_start": _iso(row.bucket_start),
            "event_category": row.event_category,
            "severity": row.severity,
            "country_code": row.country_code,
            "region": row.region,
            "city": row.city,
            "latitude": row.latitude,
            "longitude": row.longitude,
            "asn_number": row.asn_number,
            "asn_org": row.asn_org,
            "is_datacenter": row.is_datacenter,
            "count": row.count,
        }


def _export_conversion_metrics(
    db: Session, *, tenant_id: int, start: datetime, end: datetime
) -> Iterable[dict]:
    query = (
        db.query(ConversionMetric)
        .filter(
            ConversionMetric.tenant_id == tenant_id,
            ConversionMetric.captured_at >= start,
            ConversionMetric.captured_at < end,
        )
        .order_by(ConversionMetric.id.asc())
    )
    for row in query.yield_per(1000):
        yield {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "website_id": row.website_id,
            "environment_id": row.environment_id,
            "metric_key": row.metric_key,
            "window_start": _iso(row.window_start),
            "window_end": _iso(row.window_end),
            "sessions": row.sessions,
            "conversions": row.conversions,
            "conversion_rate": row.conversion_rate,
            "revenue_per_conversion": row.revenue_per_conversion,
            "captured_at": _iso(row.captured_at),
        }


def _export_notification_deliveries(
    db: Session, *, tenant_id: int, start: datetime, end: datetime
) -> Iterable[dict]:
    query = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.tenant_id == tenant_id,
            NotificationDelivery.created_at >= start,
            NotificationDelivery.created_at < end,
        )
        .order_by(NotificationDelivery.id.asc())
    )
    for row in query.yield_per(1000):
        yield {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "rule_id": row.rule_id,
            "channel_id": row.channel_id,
            "status": row.status,
            "created_at": _iso(row.created_at),
            "sent_at": _iso(row.sent_at),
            "dedupe_key": row.dedupe_key,
            "payload_json": row.payload_json,
            "error_message": row.error_message,
            "attempt_count": row.attempt_count,
        }


DATASET_EXPORTERS = {
    "incidents": _export_incidents,
    "security_events": _export_security_events,
    "geo_agg": _export_geo_agg,
    "conversion_metrics": _export_conversion_metrics,
    "notification_deliveries": _export_notification_deliveries,
}


def _ensure_schema_file(dataset_dir: Path, dataset: str) -> None:
    schema_path = dataset_dir / "schema.json"
    schema = {
        "dataset": dataset,
        "version": 1,
        "fields": DATASET_SCHEMAS.get(dataset, []),
    }
    dataset_dir.mkdir(parents=True, exist_ok=True)
    schema_path.write_text(json.dumps(schema, indent=2, sort_keys=True))


def _write_jsonl_gz(path: Path, rows: Iterable[dict]) -> int:
    bytes_written = 0
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        for row in rows:
            payload = json.dumps(row, separators=(",", ":"), sort_keys=True)
            handle.write(payload)
            handle.write("\n")
    bytes_written = path.stat().st_size
    return bytes_written


def _write_csv_gz(path: Path, rows: Iterable[dict], *, fieldnames: list[str]) -> int:
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            cleaned = {}
            for key, value in row.items():
                if isinstance(value, (dict, list)):
                    cleaned[key] = json.dumps(value, separators=(",", ":"), sort_keys=True)
                else:
                    cleaned[key] = value
            writer.writerow(cleaned)
    return path.stat().st_size


def _write_dataset_files(
    *,
    dataset: str,
    rows: Iterable[dict],
    base_dir: Path,
    tenant_id: int,
    region: str,
    date_bucket: str,
    format_value: str,
) -> tuple[int, int]:
    dataset_dir = base_dir / f"region={region}" / f"tenant={tenant_id}" / f"dataset={dataset}"
    partition_dir = dataset_dir / f"date={date_bucket}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    _ensure_schema_file(dataset_dir, dataset)

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{dataset}_{timestamp}.{format_value}"
    file_path = partition_dir / filename

    fieldnames = DATASET_SCHEMAS.get(dataset, [])
    if format_value == "jsonl.gz":
        bytes_written = _write_jsonl_gz(file_path, rows)
    elif format_value == "csv.gz":
        bytes_written = _write_csv_gz(file_path, rows, fieldnames=fieldnames)
    else:
        raise ValueError("Unsupported export format")

    return 1, bytes_written


def _dataset_rows(
    db: Session, *, dataset: str, tenant_id: int, start: datetime, end: datetime
) -> Iterable[dict]:
    exporter = DATASET_EXPORTERS.get(dataset)
    if not exporter:
        raise ValueError(f"Unsupported dataset {dataset}")
    return exporter(db, tenant_id=tenant_id, start=start, end=end)


def _determine_window(config: DataExportConfig, now: datetime) -> tuple[datetime, datetime]:
    if config.last_run_at:
        start = config.last_run_at
    else:
        lookback = settings.EXPORT_DEFAULT_LOOKBACK_HOURS
        start = now - timedelta(hours=lookback)
    return start, now


def _is_due(config: DataExportConfig, now: datetime) -> bool:
    if not config.is_enabled:
        return False
    if config.last_run_at is None:
        return True
    schedule = (config.schedule or "daily").strip().lower()
    if schedule == "hourly":
        delta = timedelta(hours=1)
    elif schedule == "weekly":
        delta = timedelta(days=7)
    else:
        delta = timedelta(days=1)
    return (now - config.last_run_at) >= delta


def run_data_exports(
    db: Session,
    *,
    now: datetime | None = None,
    base_dir: Path | None = None,
    max_configs: int = 50,
) -> int:
    now = now or utcnow()
    if base_dir is None:
        base_dir = Path(settings.EXPORT_LOCAL_DIR)
    configs = (
        db.query(DataExportConfig)
        .filter(DataExportConfig.is_enabled.is_(True))
        .order_by(DataExportConfig.id.asc())
        .limit(max_configs)
        .all()
    )
    processed = 0
    for config in configs:
        if not _is_due(config, now):
            continue
        tenant = db.query(Tenant).filter(Tenant.id == config.tenant_id).first()
        region = tenant.data_region if tenant and tenant.data_region else "us"
        datasets = config.datasets_enabled or list(DEFAULT_EXPORT_DATASETS)
        validate_export_datasets(datasets)

        run = DataExportRun(
            tenant_id=config.tenant_id,
            config_id=config.id,
            started_at=now,
            status="running",
        )
        db.add(run)
        db.commit()
        db.refresh(run)

        files_written = 0
        bytes_written = 0
        success = True
        error_message = None

        try:
            if settings.EXPORT_TARGET != "local":
                raise ValueError("Non-local export targets are not implemented yet")
            start, end = _determine_window(config, now)
            date_bucket = end.strftime("%Y-%m-%d")
            for dataset in datasets:
                rows = _dataset_rows(
                    db,
                    dataset=dataset,
                    tenant_id=config.tenant_id,
                    start=start,
                    end=end,
                )
                file_count, byte_count = _write_dataset_files(
                    dataset=dataset,
                    rows=rows,
                    base_dir=base_dir,
                    tenant_id=config.tenant_id,
                    region=region,
                    date_bucket=date_bucket,
                    format_value=config.format or "jsonl.gz",
                )
                files_written += file_count
                bytes_written += byte_count
        except Exception as exc:
            success = False
            error_message = str(exc)
            logger.exception("Data export run failed: %s", exc)

        run.finished_at = utcnow()
        run.status = "success" if success else "failed"
        run.files_written = files_written
        run.bytes_written = bytes_written
        run.error_message = error_message

        config.last_run_at = run.finished_at
        config.last_error = error_message
        db.commit()
        processed += 1

    return processed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run data export jobs.")
    parser.add_argument("--once", action="store_true", help="Run once and exit.")
    parser.add_argument("--max-configs", type=int, default=50)
    parser.add_argument("--export-dir", type=str, default=None)
    return parser.parse_args()


def main() -> None:
    from app.core.db import SessionLocal

    args = _parse_args()
    success = True
    processed = 0
    try:
        with SessionLocal() as db:
            base_dir = Path(args.export_dir) if args.export_dir else None
            processed = run_data_exports(db, base_dir=base_dir, max_configs=args.max_configs)
        logger.info("Data export run complete. processed=%s", processed)
    except Exception:
        success = False
        logger.exception("Data export job failed")
        raise
    finally:
        record_job_run(job_name="data_exports", success=success)
    if args.once:
        return


if __name__ == "__main__":
    main()
