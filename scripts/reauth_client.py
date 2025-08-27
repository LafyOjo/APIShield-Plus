#!/usr/bin/env python3
"""Demo client for the zero-trust mode requiring your password on every call.

This script talks to the demo APIShield+ server. It logs in with the username
you provide and then repeatedly calls ``/api/me``. Each call requires your
password, demonstrating the "re-authenticate every time" feature.

Example:

```
python scripts/reauth_client.py alice --base http://localhost:8001 --times 2
```

Steps for beginners:

1. Replace ``alice`` with your own username.
2. Run the command. When ``Password:`` appears, type the password you used when
   you registered and press ``Enter``.
3. The program will then ask ``Re-auth password:`` for each request. Type the
   same password again each time. Press ``Ctrl+C`` to stop whenever you like.
"""

import argparse
import getpass
import os
import requests


def login(base: str, username: str) -> tuple[str, str]:
    """Prompt for the initial password and obtain a JWT."""
    pw = getpass.getpass("Password: ")
    resp = requests.post(f"{base}/login", json={"username": username, "password": pw}, timeout=5)
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return token, pw


def call_me(base: str, token: str) -> None:
    pw = getpass.getpass("Re-auth password: ")
    headers = {"Authorization": f"Bearer {token}", "X-Reauth-Password": pw}
    resp = requests.get(f"{base}/api/me", headers=headers, timeout=5)
    print(resp.status_code, resp.json())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo client requiring the password on every request",
        epilog=(
            "Example:\n"
            "  python scripts/reauth_client.py alice --base http://localhost:8001 --times 2\n\n"
            "Steps:\n"
            "  1. Replace 'alice' with your own username.\n"
            "  2. When 'Password:' appears, type the password you used at registration.\n"
            "  3. For each request you will be asked for 'Re-auth password:' "
            "-- type the same password again.\n"
            "  Press Ctrl+C to stop the program at any time."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("username", help="Account username")
    parser.add_argument(
        "--base",
        default=os.environ.get("API_BASE", "http://localhost:8001"),
        help="API base URL",
    )
    parser.add_argument("--times", type=int, default=1, help="Number of requests to send")
    args = parser.parse_args()

    print(
        f"\nConnecting to {args.base} as '{args.username}'. "
        "You will be asked for your password now and then again for each request."
    )

    token, _ = login(args.base, args.username)
    for _ in range(args.times):
        call_me(args.base, token)


if __name__ == "__main__":
    main()
