"""Prove local container readiness and AOF persistence without a model call."""
import json
import subprocess
import time
import urllib.error
import urllib.request


def loaded(deadline=600):
    started = time.monotonic()
    while time.monotonic() - started < deadline:
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=15) as response:
                health = json.load(response)
                if health.get("accounts", 0) > 0 and health.get("seed_complete", True):
                    return health
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(3)
    raise SystemExit("Smoke failed: graph did not become ready within 10 minutes")


before = loaded()
subprocess.run(["docker", "compose", "restart", "falkordb"], check=True)
after = loaded(180)
assert before["accounts"] == after["accounts"], "Account count changed across DB restart"
print(json.dumps({"smoke": "pass", "accounts": after["accounts"], "persistence": "pass"}))
