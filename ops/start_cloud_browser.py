"""Start a loopback-only FalkorDB Browser connected to the live synthetic graph.

The database URL is inherited by Docker through an environment variable; it is
never placed in process arguments or output. This starts no paid service and
does not seed or change the Cloud graph. Stop with: docker stop ringsight-browser.
"""
import os
from pathlib import Path
import subprocess

from dotenv import load_dotenv


def main():
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env", override=True)
    url = os.getenv("REDIS_URL")
    if not url:
        raise SystemExit("REDIS_URL is absent from the environment.")
    env = os.environ.copy()
    env["FALKORDB_CONNECTION_URL"] = url
    # The pinned all-in-one image contains Browser; its unused local Redis is
    # not published. Only Browser is exposed, on loopback.
    result = subprocess.run([
        "docker", "run", "--detach", "--rm", "--name", "ringsight-browser",
        "--publish", "127.0.0.1:3002:3000", "--env", "FALKORDB_CONNECTION_URL",
        "falkordb/falkordb:v4.22.1",
    ], env=env, capture_output=True, text=True, timeout=120)
    if result.returncode:
        # Docker errors may include environment details; never print them.
        raise SystemExit("Browser did not start. If ringsight-browser already exists, use its existing http://127.0.0.1:3002 page or stop it before retrying.")
    print("FalkorDB Browser: http://127.0.0.1:3002 (live synthetic graph; loopback only)")


if __name__ == "__main__":
    main()
