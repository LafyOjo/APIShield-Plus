from pathlib import Path
from uuid import UUID

import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

from scripts.load.gen_events import (
    EventGeneratorConfig,
    SessionPool,
    TargetConfig,
    build_event,
)


def test_load_harness_generates_valid_event_payloads():
    target = TargetConfig(api_key="pk_test", domain="example.com", weight=1)
    config = EventGeneratorConfig(
        event_mix=[{"type": "page_view", "weight": 1}],
        path_pool=["/checkout"],
        referrers=[None],
        session_pool_size=5,
    )
    session_pool = SessionPool(5, rng=__import__("random").Random(1))
    event = build_event(
        target=target,
        config=config,
        rng=__import__("random").Random(2),
        session_pool=session_pool,
    )

    UUID(event["event_id"])
    assert event["type"] == "page_view"
    assert event["url"].startswith("https://example.com")
    assert event["path"].startswith("/")
    assert event["session_id"].startswith("s_")


def test_load_harness_generates_security_event_payloads():
    target = TargetConfig(api_key="pk_test", domain="example.com", weight=1)
    config = EventGeneratorConfig(
        event_mix=[{"type": "login_attempt_failed", "weight": 1}],
        path_pool=["/login"],
        referrers=[None],
        session_pool_size=5,
    )
    session_pool = SessionPool(5, rng=__import__("random").Random(1))
    event = build_event(
        target=target,
        config=config,
        rng=__import__("random").Random(2),
        session_pool=session_pool,
    )

    assert event["event_type"] == "login_attempt_failed"
    assert event["severity"] in {"low", "medium", "high", "critical"}
    assert event["request_path"].startswith("/")
