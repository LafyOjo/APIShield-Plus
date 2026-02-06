import argparse
import asyncio
import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Any

import httpx

from scripts.load.gen_events import (
    DEFAULT_EVENT_MIX,
    DEFAULT_PATH_POOL,
    DEFAULT_REFERRERS,
    EventGeneratorConfig,
    SessionPool,
    TargetConfig,
    build_event,
    build_targets,
    choose_target,
)


DEFAULT_BUCKETS_MS = [
    1,
    2,
    5,
    10,
    25,
    50,
    100,
    250,
    500,
    1000,
    2000,
    5000,
    10000,
]


def _parse_labels(raw: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not raw:
        return labels
    for part in raw.split(","):
        part = part.strip()
        if not part or "=" not in part:
            continue
        key, value = part.split("=", 1)
        labels[key.strip()] = value.strip().strip('"')
    return labels


def _scrape_metrics(base_url: str, metrics_path: str) -> dict[str, Any]:
    url = f"{base_url}{metrics_path}"
    payload = {
        "queue_depth": {},
        "slow_query_total": 0.0,
    }
    try:
        resp = httpx.get(url, timeout=5.0)
        if resp.status_code != 200:
            return payload
    except Exception:
        return payload
    for line in resp.text.splitlines():
        if not line or line.startswith("#"):
            continue
        if " " not in line:
            continue
        metric_part, value_part = line.split(" ", 1)
        value_part = value_part.strip()
        try:
            value = float(value_part)
        except ValueError:
            continue
        if metric_part.startswith("queue_depth"):
            labels_raw = ""
            if "{" in metric_part and metric_part.endswith("}"):
                name, labels_raw = metric_part.split("{", 1)
                labels_raw = labels_raw[:-1]
            else:
                name = metric_part
            if name != "queue_depth":
                continue
            labels = _parse_labels(labels_raw)
            queue_name = labels.get("queue", "unknown")
            payload["queue_depth"][queue_name] = value
            continue
        if metric_part.startswith("slow_query_total"):
            payload["slow_query_total"] = value
    return payload


def _drain_queue_depth(
    *,
    base_url: str,
    metrics_path: str,
    queues: list[str],
    threshold: float,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any]:
    start = time.monotonic()
    elapsed = 0.0
    while elapsed <= timeout_seconds:
        metrics = _scrape_metrics(base_url, metrics_path)
        depths = metrics.get("queue_depth", {})
        if all(float(depths.get(queue, 0.0)) <= threshold for queue in queues):
            return {
                "success": True,
                "seconds": round(elapsed, 2),
                "queue_depth": depths,
            }
        time.sleep(max(0.5, poll_interval_seconds))
        elapsed = time.monotonic() - start
    return {
        "success": False,
        "seconds": round(elapsed, 2),
        "queue_depth": _scrape_metrics(base_url, metrics_path).get("queue_depth", {}),
    }


@dataclass
class LatencyStats:
    buckets: list[int] = field(default_factory=lambda: DEFAULT_BUCKETS_MS.copy())
    counts: list[int] = field(init=False)
    total: int = 0
    total_ms: float = 0.0
    min_ms: float | None = None
    max_ms: float | None = None

    def __post_init__(self):
        self.counts = [0] * (len(self.buckets) + 1)

    def observe(self, duration_ms: float) -> None:
        self.total += 1
        self.total_ms += duration_ms
        if self.min_ms is None or duration_ms < self.min_ms:
            self.min_ms = duration_ms
        if self.max_ms is None or duration_ms > self.max_ms:
            self.max_ms = duration_ms
        idx = 0
        while idx < len(self.buckets) and duration_ms > self.buckets[idx]:
            idx += 1
        self.counts[idx] += 1

    def percentile(self, pct: float) -> float | None:
        if self.total == 0:
            return None
        target = math.ceil(self.total * (pct / 100.0))
        cumulative = 0
        for idx, count in enumerate(self.counts):
            cumulative += count
            if cumulative >= target:
                if idx >= len(self.buckets):
                    return float(self.buckets[-1])
                return float(self.buckets[idx])
        return float(self.buckets[-1])

    def merge(self, other: "LatencyStats") -> None:
        if self.buckets != other.buckets:
            raise ValueError("Bucket mismatch")
        self.total += other.total
        self.total_ms += other.total_ms
        if other.min_ms is not None:
            if self.min_ms is None or other.min_ms < self.min_ms:
                self.min_ms = other.min_ms
        if other.max_ms is not None:
            if self.max_ms is None or other.max_ms > self.max_ms:
                self.max_ms = other.max_ms
        self.counts = [a + b for a, b in zip(self.counts, other.counts)]

    def to_dict(self) -> dict[str, Any]:
        avg_ms = (self.total_ms / self.total) if self.total else None
        return {
            "count": self.total,
            "min_ms": round(self.min_ms, 2) if self.min_ms is not None else None,
            "max_ms": round(self.max_ms, 2) if self.max_ms is not None else None,
            "avg_ms": round(avg_ms, 2) if avg_ms is not None else None,
            "p50_ms": self.percentile(50),
            "p95_ms": self.percentile(95),
            "p99_ms": self.percentile(99),
            "buckets_ms": self.buckets,
            "counts": self.counts,
        }


@dataclass
class RunStats:
    requests: int = 0
    events: int = 0
    errors: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    latency: LatencyStats = field(default_factory=LatencyStats)

    def observe(self, status_code: int, duration_ms: float, events: int) -> None:
        self.requests += 1
        self.events += events
        self.status_counts[str(status_code)] = self.status_counts.get(str(status_code), 0) + 1
        if status_code >= 400:
            self.errors += 1
        self.latency.observe(duration_ms)

    def merge(self, other: "RunStats") -> None:
        self.requests += other.requests
        self.events += other.events
        self.errors += other.errors
        for code, count in other.status_counts.items():
            self.status_counts[code] = self.status_counts.get(code, 0) + count
        self.latency.merge(other.latency)

    def to_dict(self) -> dict[str, Any]:
        error_rate = (self.errors / self.requests) if self.requests else 0.0
        payload = {
            "requests": self.requests,
            "events": self.events,
            "errors": self.errors,
            "error_rate": round(error_rate * 100, 3),
            "status_codes": self.status_counts,
            "latency_ms": self.latency.to_dict(),
        }
        return payload


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_generator_config(config: dict[str, Any]) -> EventGeneratorConfig:
    return EventGeneratorConfig(
        event_mix=config.get("event_mix") or DEFAULT_EVENT_MIX,
        path_pool=config.get("path_pool") or DEFAULT_PATH_POOL,
        referrers=config.get("referrers") or DEFAULT_REFERRERS,
        session_pool_size=int(config.get("session_pool_size") or 1000),
    )


async def _run_segment(
    *,
    client: httpx.AsyncClient,
    base_url: str,
    ingest_path: str,
    security_ingest_path: str,
    security_auth_header: str,
    targets: list[TargetConfig],
    generator: EventGeneratorConfig,
    session_pool: SessionPool,
    rps: int,
    duration_seconds: int,
    batch_size: int,
    max_in_flight: int,
    rng: random.Random,
    stats: RunStats,
) -> None:
    if rps <= 0 or duration_seconds <= 0:
        return
    requests_per_second = max(1.0, rps / max(1, batch_size))
    interval = 1.0 / requests_per_second
    end_time = time.monotonic() + duration_seconds
    semaphore = asyncio.Semaphore(max_in_flight)
    tasks: set[asyncio.Task] = set()

    async def send_payload(payload: dict[str, Any], *, url: str, headers: dict[str, str], event_count: int) -> None:
        start = time.perf_counter()
        status_code = 0
        try:
            resp = await client.post(url, json=payload, headers=headers)
            status_code = resp.status_code
        except Exception:
            status_code = 599
        duration_ms = (time.perf_counter() - start) * 1000.0
        stats.observe(status_code, duration_ms, event_count)

    async def emit_one():
        async with semaphore:
            target = choose_target(targets, rng=rng)
            batch = []
            for _ in range(batch_size):
                batch.append(
                    build_event(
                        target=target,
                        config=generator,
                        rng=rng,
                        session_pool=session_pool,
                    )
                )
            browser_events = [event for event in batch if "event_type" not in event]
            security_events = [event for event in batch if "event_type" in event]

            if browser_events:
                headers = {"X-Api-Key": target.api_key}
                payload = {"events": browser_events} if len(browser_events) > 1 else browser_events[0]
                await send_payload(
                    payload,
                    url=f"{base_url}{ingest_path}",
                    headers=headers,
                    event_count=len(browser_events),
                )

            if security_events:
                auth_header = security_auth_header
                auth_value = target.api_key
                if auth_header.lower() == "x-api-secret":
                    if target.api_secret:
                        auth_value = target.api_secret
                    else:
                        auth_header = "X-Api-Key"
                        auth_value = target.api_key
                headers = {auth_header: auth_value}
                for event in security_events:
                    await send_payload(
                        event,
                        url=f"{base_url}{security_ingest_path}",
                        headers=headers,
                        event_count=1,
                    )

    next_send = time.monotonic()
    while time.monotonic() < end_time:
        now = time.monotonic()
        if now < next_send:
            await asyncio.sleep(min(interval, next_send - now))
            continue
        task = asyncio.create_task(emit_one())
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        next_send += interval

    if tasks:
        await asyncio.gather(*tasks)


async def _run_worker_async(worker_id: int, config: dict[str, Any]) -> dict[str, Any]:
    base_url = config.get("base_url", "http://localhost:8000")
    ingest_path = config.get("ingest_path", "/api/v1/ingest/browser")
    security_ingest_path = config.get("security_ingest_path", "/api/v1/ingest/integrity")
    security_auth_header = config.get("security_auth_header", "X-Api-Key")
    targets = build_targets(config.get("targets") or [])
    if not targets:
        raise ValueError("Scenario has no targets with api_key + domain.")

    generator = _build_generator_config(config)
    rng = random.Random(worker_id + int(time.time()))
    session_pool = SessionPool(generator.session_pool_size, rng=rng)

    batch_size = int(config.get("batch_size") or 1)
    max_in_flight = int(config.get("max_in_flight") or 100)
    stats = RunStats()

    async with httpx.AsyncClient(timeout=float(config.get("timeout_seconds") or 10.0)) as client:
        segments = config.get("segments") or []
        for segment in segments:
            await _run_segment(
                client=client,
                base_url=base_url,
                ingest_path=ingest_path,
                security_ingest_path=security_ingest_path,
                security_auth_header=security_auth_header,
                targets=targets,
                generator=generator,
                session_pool=session_pool,
                rps=int(segment.get("rps") or 0),
                duration_seconds=int(segment.get("duration_seconds") or 0),
                batch_size=batch_size,
                max_in_flight=max_in_flight,
                rng=rng,
                stats=stats,
            )

    return {
        "worker_id": worker_id,
        "stats": stats.to_dict(),
    }


def _worker_entry(worker_id: int, config: dict[str, Any], result_queue: Queue) -> None:
    result = asyncio.run(_run_worker_async(worker_id, config))
    result_queue.put(result)


def _merge_worker_stats(worker_results: list[dict[str, Any]]) -> RunStats:
    merged = RunStats()
    for result in worker_results:
        stats = result.get("stats") or {}
        latency = stats.get("latency_ms") or {}
        buckets = latency.get("buckets_ms") or DEFAULT_BUCKETS_MS
        counts = latency.get("counts") or [0] * (len(buckets) + 1)
        lat = LatencyStats(buckets=buckets)
        lat.counts = counts
        lat.total = latency.get("count") or 0
        lat.total_ms = (lat.total * (latency.get("avg_ms") or 0.0))
        lat.min_ms = latency.get("min_ms")
        lat.max_ms = latency.get("max_ms")

        part = RunStats(
            requests=stats.get("requests", 0),
            events=stats.get("events", 0),
            errors=stats.get("errors", 0),
            status_counts=stats.get("status_codes", {}),
            latency=lat,
        )
        merged.merge(part)
    return merged


def _summary_markdown(config: dict[str, Any], stats: RunStats, metrics: dict[str, Any] | None) -> str:
    latency = stats.latency.to_dict()
    error_rate = stats.errors / stats.requests if stats.requests else 0.0
    p99 = latency.get("p99_ms")
    pass_errors = error_rate <= 0.005
    pass_p99 = (p99 or 0) <= 500
    metrics = metrics or {}
    drain = metrics.get("drain") or {}
    queue_after = (metrics.get("after") or {}).get("queue_depth") or {}
    slow_query_delta = metrics.get("slow_query_delta")
    drain_status = (
        "PASS" if drain and drain.get("success") else "FAIL" if drain else "N/A"
    )
    return "\n".join(
        [
            f"# Load Test Report: {config.get('name', 'scenario')}",
            "",
            f"- Base URL: `{config.get('base_url')}`",
            f"- Requests: {stats.requests}",
            f"- Events: {stats.events}",
            f"- Errors: {stats.errors} ({error_rate * 100:.3f}%)",
            f"- p50: {latency.get('p50_ms')} ms",
            f"- p95: {latency.get('p95_ms')} ms",
            f"- p99: {latency.get('p99_ms')} ms",
            f"- Slow query delta: {slow_query_delta}",
            "",
            "## Queue Depth (After)",
            json.dumps(queue_after, indent=2),
            "",
            "## Thresholds",
            f"- Error rate < 0.5%: {'PASS' if pass_errors else 'FAIL'}",
            f"- Ingest p99 < 500ms: {'PASS' if pass_p99 else 'FAIL'}",
            f"- Backlog drain within window: {drain_status}",
            "",
            "## Status Codes",
            json.dumps(stats.status_counts, indent=2),
        ]
    )


def run_scenario(config: dict[str, Any]) -> dict[str, Any]:
    workers = int(config.get("workers") or 1)
    result_queue: Queue = Queue()
    processes: list[Process] = []
    metrics_path = config.get("metrics_path", "/metrics")
    base_url = config.get("base_url", "http://localhost:8000")
    metrics_before = _scrape_metrics(base_url, metrics_path)

    for worker_id in range(workers):
        proc = Process(target=_worker_entry, args=(worker_id, config, result_queue))
        proc.start()
        processes.append(proc)

    worker_results = [result_queue.get() for _ in processes]
    for proc in processes:
        proc.join()

    metrics_after = _scrape_metrics(base_url, metrics_path)
    slow_query_delta = max(
        0.0, metrics_after.get("slow_query_total", 0.0) - metrics_before.get("slow_query_total", 0.0)
    )
    drain_check = config.get("drain_check") or {}
    drain_result = None
    if drain_check:
        queues = drain_check.get("queues") or ["critical", "standard", "bulk"]
        threshold = float(drain_check.get("threshold") or 0.0)
        timeout_seconds = int(drain_check.get("timeout_seconds") or 600)
        poll_interval_seconds = int(drain_check.get("poll_interval_seconds") or 10)
        drain_result = _drain_queue_depth(
            base_url=base_url,
            metrics_path=metrics_path,
            queues=queues,
            threshold=threshold,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    merged = _merge_worker_stats(worker_results)
    output = {
        "name": config.get("name"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "workers": worker_results,
        "summary": merged.to_dict(),
        "metrics": {
            "before": metrics_before,
            "after": metrics_after,
            "slow_query_delta": slow_query_delta,
            "drain": drain_result,
        },
    }
    return output


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest load test runner")
    parser.add_argument("--scenario", required=True, help="Path to scenario JSON")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--output-md", default=None)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    scenario_path = Path(args.scenario)
    config = _load_json(scenario_path)
    if args.base_url:
        config["base_url"] = args.base_url
    output = run_scenario(config)
    summary_stats = _merge_worker_stats(output.get("workers", []))

    output_json = args.output_json or config.get("output_json")
    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as handle:
            json.dump(output, handle, indent=2)
    else:
        print(json.dumps(output, indent=2))

    output_md = args.output_md or config.get("output_md")
    if output_md:
        summary = _summary_markdown(config, summary_stats, output.get("metrics"))
        Path(output_md).parent.mkdir(parents=True, exist_ok=True)
        with open(output_md, "w", encoding="utf-8") as handle:
            handle.write(summary)


if __name__ == "__main__":
    main()
