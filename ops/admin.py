"""Authenticated operations without putting secrets in command-line arguments."""
import argparse
import json
import os

import httpx
from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("halt", "resume", "model-off", "model-on", "reseed", "reseed-force", "algo-refresh"))
    parser.add_argument("--url", default=os.getenv("PUBLIC_URL") or "http://127.0.0.1:8000")
    args = parser.parse_args()
    token = os.environ.get("ADMIN_TOKEN")
    if not token:
        raise SystemExit("ADMIN_TOKEN must be set in the environment or .env")
    route, body = {
        "halt": ("/admin/halt", {"halted": True}),
        "resume": ("/admin/halt", {"halted": False}),
        "model-off": ("/admin/llm", {"enabled": False}),
        "model-on": ("/admin/llm", {"enabled": True}),
        "reseed": ("/admin/reseed", {}),
        "reseed-force": ("/admin/reseed?force=1", {}),
        "algo-refresh": ("/admin/algo_refresh", {}),
    }[args.action]
    try:
        response = httpx.post(args.url.rstrip("/") + route, json=body, headers={"Authorization": "Bearer " + token}, timeout=30)
        print(json.dumps({"status_code": response.status_code, "result": response.json()}))
        response.raise_for_status()
    except (httpx.HTTPError, ValueError):
        raise SystemExit("Operation did not succeed; inspect /health and the server log.") from None


if __name__ == "__main__":
    main()
