import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx


DEFAULT_ENDPOINTS = [
    {"name": "incidents_list", "method": "GET", "path": "/api/v1/incidents"},
    {"name": "incident_detail", "method": "GET", "path": "/api/v1/incidents/{incident_id}"},
    {"name": "map_summary", "method": "GET", "path": "/api/v1/map/summary"},
    {"name": "map_drilldown", "method": "GET", "path": "/api/v1/map/drilldown"},
    {"name": "revenue_leaks", "method": "GET", "path": "/api/v1/revenue/leaks"},
    {"name": "trust_snapshots", "method": "GET", "path": "/api/v1/trust/snapshots"},
]

SMOKE_ENDPOINTS = [
    {"name": "ping", "method": "GET", "path": "/ping"},
    {"name": "health", "method": "GET", "path": "/api/v1/health"},
]


def percentile(values, pct):
    if not values:
        return None
    values = sorted(values)
    k = max(0, min(len(values) - 1, int(round((pct / 100.0) * (len(values) - 1)))))
    return values[k]


def build_params(name, now, windows):
    if name in {"map_summary", "map_drilldown"}:
        return {
            "from": (now - timedelta(hours=windows["map_hours"])).isoformat(),
            "to": now.isoformat(),
        }
    if name in {"revenue_leaks", "trust_snapshots"}:
        return {
            "from": (now - timedelta(days=windows["analytics_days"])).isoformat(),
            "to": now.isoformat(),
        }
    return {}


def render_markdown_report(report):
    lines = [
        "# APIShield+ Benchmark Report",
        "",
        f"Generated at: {report.get('generated_at')}",
        f"Base URL: {report.get('base_url')}",
        f"Requests per endpoint: {report.get('requests_per_endpoint')}",
        f"Concurrency: {report.get('concurrency')}",
        "",
        "| Endpoint | Requests | Errors | p50 (ms) | p95 (ms) | p99 (ms) | Avg (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for name, data in report.get("endpoints", {}).items():
        if data.get("skipped"):
            lines.append(
                f"| {name} | 0 | 0 | - | - | - | - |"
            )
            continue
        lines.append(
            "| {name} | {requests} | {errors} | {p50} | {p95} | {p99} | {avg} |".format(
                name=name,
                requests=data.get("requests", 0),
                errors=data.get("errors", 0),
                p50=data.get("p50_ms", "-"),
                p95=data.get("p95_ms", "-"),
                p99=data.get("p99_ms", "-"),
                avg=data.get("avg_ms", "-"),
            )
        )

    return "\n".join(lines) + "\n"


def write_report(report, *, json_path=None, markdown_path=None):
    if json_path:
        json_path = Path(json_path)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if markdown_path:
        markdown_path = Path(markdown_path)
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(render_markdown_report(report), encoding="utf-8")


def _build_report_paths(args):
    json_path = Path(args.output) if args.output else None
    markdown_path = Path(args.markdown) if args.markdown else None

    if args.report_dir:
        report_dir = Path(args.report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        if json_path is None:
            json_path = report_dir / "bench_report.json"
        if markdown_path is None:
            markdown_path = report_dir / "bench_report.md"

    return json_path, markdown_path


def load_bench_config(config_path: str | None):
    if not config_path:
        return None
    path = Path(config_path)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def evaluate_smoke(report, *, error_rate_threshold=5.0, p99_threshold_ms=3000.0):
    endpoints = report.get("endpoints", {})
    total_requests = 0
    total_errors = 0
    max_p99 = None

    for data in endpoints.values():
        if data.get("skipped") or data.get("optional"):
            continue
        requests = data.get("requests") or 0
        errors = data.get("errors") or 0
        total_requests += requests
        total_errors += errors
        p99 = data.get("p99_ms")
        if p99 is not None:
            max_p99 = p99 if max_p99 is None else max(max_p99, p99)

    error_rate_pct = (
        round((total_errors / total_requests) * 100.0, 2) if total_requests else 0.0
    )
    failed = False
    if error_rate_pct > error_rate_threshold:
        failed = True
    if max_p99 is not None and max_p99 > p99_threshold_ms:
        failed = True

    return {
        "total_requests": total_requests,
        "total_errors": total_errors,
        "error_rate_pct": error_rate_pct,
        "max_p99_ms": max_p99,
        "failed": failed,
        "thresholds": {
            "error_rate_pct": error_rate_threshold,
            "p99_ms": p99_threshold_ms,
        },
    }


async def resolve_incident_id(client, base_url, headers):
    resp = await client.get(
        f"{base_url}/api/v1/incidents", headers=headers, params={"limit": 1}
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("id")
    return None


async def _run_requests(
    client,
    endpoint,
    *,
    base_url,
    headers,
    params,
    requests_count,
    concurrency,
    incident_id,
    record,
):
    latencies = []
    status_counts = {}
    errors = 0
    completed = 0

    async def worker():
        nonlocal errors, completed
        path = endpoint["path"]
        if "{incident_id}" in path:
            if not incident_id:
                return
            path = path.replace("{incident_id}", str(incident_id))
        url = f"{base_url}{path}"
        start = time.monotonic()
        try:
            resp = await client.request(
                endpoint["method"], url, headers=headers, params=params
            )
            duration_ms = (time.monotonic() - start) * 1000.0
            if record:
                latencies.append(duration_ms)
            status_counts[str(resp.status_code)] = (
                status_counts.get(str(resp.status_code), 0) + 1
            )
            if resp.status_code >= 400:
                errors += 1
        except Exception:
            errors += 1
        finally:
            completed += 1

    semaphore = asyncio.Semaphore(concurrency)

    async def wrapped():
        async with semaphore:
            await worker()

    tasks = [asyncio.create_task(wrapped()) for _ in range(requests_count)]
    await asyncio.gather(*tasks)

    return latencies, status_counts, errors, completed


async def run_endpoint(
    client,
    endpoint,
    *,
    base_url,
    headers,
    params,
    requests_count,
    concurrency,
    incident_id,
    warmup,
):
    if "{incident_id}" in endpoint["path"] and not incident_id:
        return {"skipped": True, "reason": "missing_incident_id"}

    if warmup:
        await _run_requests(
            client,
            endpoint,
            base_url=base_url,
            headers=headers,
            params=params,
            requests_count=warmup,
            concurrency=concurrency,
            incident_id=incident_id,
            record=False,
        )

    if requests_count <= 0:
        return {"requests": 0, "errors": 0, "status_codes": {}}

    latencies, status_counts, errors, completed = await _run_requests(
        client,
        endpoint,
        base_url=base_url,
        headers=headers,
        params=params,
        requests_count=requests_count,
        concurrency=concurrency,
        incident_id=incident_id,
        record=True,
    )

    if not latencies:
        return {
            "requests": completed,
            "errors": errors,
            "status_codes": status_counts,
            "error_rate_pct": round((errors / completed) * 100.0, 2) if completed else 0.0,
        }

    result = {
        "requests": completed,
        "errors": errors,
        "status_codes": status_counts,
        "min_ms": round(min(latencies), 2),
        "max_ms": round(max(latencies), 2),
        "avg_ms": round(sum(latencies) / len(latencies), 2),
        "p50_ms": round(percentile(latencies, 50), 2),
        "p95_ms": round(percentile(latencies, 95), 2),
        "p99_ms": round(percentile(latencies, 99), 2),
        "error_rate_pct": round((errors / completed) * 100.0, 2) if completed else 0.0,
    }
    return result


async def run_bench(args):
    token = args.token or os.getenv("BENCH_TOKEN") or os.getenv("API_TOKEN")
    tenant = args.tenant or os.getenv("BENCH_TENANT_ID") or os.getenv("TENANT_ID")
    username = args.username or os.getenv("BENCH_USERNAME")
    password = args.password or os.getenv("BENCH_PASSWORD")

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if tenant:
        headers["X-Tenant-ID"] = tenant

    config = load_bench_config(args.config)
    if config:
        endpoints = config.get("smoke") if args.smoke else config.get("endpoints")
        if not endpoints:
            endpoints = SMOKE_ENDPOINTS if args.smoke else DEFAULT_ENDPOINTS
        windows = config.get("default_windows", {})
    else:
        endpoints = SMOKE_ENDPOINTS if args.smoke else DEFAULT_ENDPOINTS
        windows = {}
    windows = {
        "map_hours": windows.get("map_hours", 24),
        "analytics_days": windows.get("analytics_days", 7),
    }
    if args.only:
        endpoints = [ep for ep in endpoints if ep["name"] in args.only]

    client_kwargs = {"timeout": args.timeout, "base_url": args.base_url}
    if args.asgi:
        from app.main import app

        client_kwargs["app"] = app

    async with httpx.AsyncClient(**client_kwargs) as client:
        if not token and username and password:
            login_headers = {"X-Tenant-ID": tenant} if tenant else {}
            login_resp = await client.post(
                f"{args.base_url}{args.login_path}",
                json={"username": username, "password": password},
                headers=login_headers,
            )
            login_resp.raise_for_status()
            token = login_resp.json().get("access_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"

        incident_id = args.incident_id
        if not incident_id and any("{incident_id}" in ep["path"] for ep in endpoints):
            incident_id = await resolve_incident_id(client, args.base_url, headers)

        results = {}
        now = datetime.utcnow()
        for endpoint in endpoints:
            params = endpoint.get("params") or build_params(endpoint["name"], now, windows)
            result = await run_endpoint(
                client,
                endpoint,
                base_url=args.base_url,
                headers=headers,
                params=params,
                requests_count=args.requests,
                concurrency=args.concurrency,
                incident_id=incident_id,
                warmup=args.warmup,
            )
            if endpoint.get("optional"):
                result["optional"] = True
                if endpoint.get("reason"):
                    result["optional_reason"] = endpoint["reason"]
            results[endpoint["name"]] = result

    output = {
        "generated_at": datetime.utcnow().isoformat(),
        "base_url": args.base_url,
        "requests_per_endpoint": args.requests,
        "concurrency": args.concurrency,
        "endpoints": results,
    }
    if args.smoke:
        output["smoke"] = evaluate_smoke(output)

    json_path, markdown_path = _build_report_paths(args)
    if json_path or markdown_path:
        write_report(output, json_path=json_path, markdown_path=markdown_path)
    if json_path is None:
        print(json.dumps(output, indent=2))
    if args.smoke and output.get("smoke", {}).get("failed"):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description="APIShield+ benchmark runner")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--token", default=None)
    parser.add_argument("--tenant", default=None)
    parser.add_argument("--username", default=None)
    parser.add_argument("--password", default=None)
    parser.add_argument("--incident-id", type=int, default=None)
    parser.add_argument("--requests", type=int, default=None)
    parser.add_argument("--concurrency", type=int, default=None)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", default=None)
    parser.add_argument("--markdown", default=None)
    parser.add_argument("--report-dir", default=None)
    parser.add_argument("--login-path", default="/api/v1/login")
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("benchmarks.json")),
        help="Path to benchmarks.json",
    )
    parser.add_argument("--asgi", action="store_true", help="Run against ASGI app in-process")
    parser.add_argument("--smoke", action="store_true", help="Run a minimal health-only sweep")
    parser.add_argument(
        "--only",
        nargs="*",
        help="Run only specific endpoint names (e.g., incidents_list map_summary)",
    )
    args = parser.parse_args()
    if args.smoke:
        if args.requests is None:
            args.requests = 10
        if args.concurrency is None:
            args.concurrency = 2
    else:
        if args.requests is None:
            args.requests = 30
        if args.concurrency is None:
            args.concurrency = 5
    asyncio.run(run_bench(args))


if __name__ == "__main__":
    main()
