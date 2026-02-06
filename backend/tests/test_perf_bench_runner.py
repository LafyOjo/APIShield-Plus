import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts.perf import bench


def test_bench_runner_writes_reports(tmp_path):
    report = {
        "generated_at": "2026-02-10T12:00:00Z",
        "base_url": "http://example.com",
        "requests_per_endpoint": 3,
        "concurrency": 1,
        "endpoints": {
            "ping": {
                "requests": 3,
                "errors": 0,
                "status_codes": {"200": 3},
                "min_ms": 1.0,
                "max_ms": 2.0,
                "avg_ms": 1.5,
                "p50_ms": 1.5,
                "p95_ms": 2.0,
                "p99_ms": 2.0,
                "error_rate_pct": 0.0,
            }
        },
    }
    json_path = tmp_path / "bench.json"
    md_path = tmp_path / "bench.md"

    bench.write_report(report, json_path=json_path, markdown_path=md_path)

    assert json_path.exists()
    assert md_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["base_url"] == "http://example.com"
    assert "APIShield+ Benchmark Report" in md_path.read_text(encoding="utf-8")


def test_bench_smoke_evaluation_flags_failures():
    report = {
        "endpoints": {
            "ping": {"requests": 10, "errors": 1, "p99_ms": 1200},
        }
    }
    result = bench.evaluate_smoke(report)
    assert result["failed"] is True

    report = {
        "endpoints": {
            "ping": {"requests": 10, "errors": 0, "p99_ms": 3500},
        }
    }
    result = bench.evaluate_smoke(report)
    assert result["failed"] is True

    report = {
        "endpoints": {
            "ping": {"requests": 10, "errors": 0, "p99_ms": 250},
        }
    }
    result = bench.evaluate_smoke(report)
    assert result["failed"] is False
