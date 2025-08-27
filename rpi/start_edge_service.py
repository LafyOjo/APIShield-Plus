import os
import signal
import subprocess
import sys
from pathlib import Path


def get_local_ip() -> str:
    try:
        out = subprocess.check_output(["hostname", "-I"], text=True)
        return out.split()[0]
    except Exception:
        return "localhost"


def main():
    repo = Path(__file__).resolve().parents[1]

    # Load backend env vars if .env exists
    env_file = repo / "backend" / ".env"
    backend_env = os.environ.copy()
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                backend_env[key] = value

    backend_proc = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=repo / "backend",
        env=backend_env,
    )

    ip = get_local_ip()
    frontend_env = os.environ.copy()
    frontend_env.update({"HOST": "0.0.0.0", "REACT_APP_API_BASE": f"http://{ip}:8001"})

    try:
        subprocess.call(
            ["npm", "start"],
            cwd=repo / "frontend",
            env=frontend_env,
        )
    finally:
        backend_proc.send_signal(signal.SIGINT)
        backend_proc.wait()


if __name__ == "__main__":
    main()
