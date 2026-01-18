from urllib.parse import urlsplit


def normalize_domain(value: str) -> str:
    if not value or not value.strip():
        raise ValueError("Domain is required.")

    raw = value.strip()
    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("Domain must not include a path.")
        candidate = parsed.netloc or parsed.path
    else:
        candidate = raw

    candidate = candidate.strip().rstrip("/").lower()
    if not candidate or "/" in candidate or "?" in candidate or "#" in candidate:
        raise ValueError("Domain must not include a path.")
    return candidate
