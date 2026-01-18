"""
Utility to inventory FastAPI routes and persist them for audit docs.

It imports the application, walks the routing table (including websockets),
and writes a tab-separated list to docs/tenancy/route_inventory.txt.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable, Tuple

from fastapi.routing import APIWebSocketRoute, APIRoute


ROOT = Path(__file__).resolve().parents[1]

# Ensure required settings exist so imports succeed even outside docker/env files.
os.environ.setdefault("DATABASE_URL", f"sqlite:///{(ROOT / 'backend' / 'app.db').as_posix()}")
os.environ.setdefault("SECRET_KEY", "route-listing-placeholder")

# Make backend package importable when running from repo root.
sys.path.append(str(ROOT / "backend"))

from app.main import app  # type: ignore  # noqa: E402


def iter_routes() -> Iterable[Tuple[str, str, str, str]]:
    """Yield (kind, methods, path, endpoint) for HTTP and websocket routes."""
    for route in app.routes:
        if isinstance(route, APIRoute):
            methods = sorted(m for m in route.methods or [] if m not in {"HEAD", "OPTIONS"})
            endpoint = getattr(route.endpoint, "__name__", route.name or "")
            yield ("HTTP", ",".join(methods) or "GET", route.path, endpoint)
        elif isinstance(route, APIWebSocketRoute):
            endpoint = getattr(route.endpoint, "__name__", route.name or "")
            yield ("WS", "WS", route.path, endpoint)


def write_routes(out_path: Path) -> list[str]:
    """Write route inventory to ``out_path`` and return written lines."""
    lines = [f"{kind}\t{methods}\t{path}\t{endpoint}" for kind, methods, path, endpoint in iter_routes()]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return lines


def main() -> None:
    out_path = ROOT / "docs" / "tenancy" / "route_inventory.txt"
    lines = write_routes(out_path)
    print(f"Wrote {len(lines)} routes to {out_path}")


if __name__ == "__main__":
    main()
