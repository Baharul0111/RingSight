"""One-command isolated Docker build, AOF smoke and headless browser proof.

Run: .venv/bin/python ops/verify_compose.py

Every child receives project rs_acceptance and loopback app/Redis/Browser
ports 18000/16379/13000 explicitly. No shell export is required. Existing dev
services are left running. No investigation is submitted; the real UI may
cause the application's tiny cached health-readiness probe. The built image
uses the same Dockerfile as Render.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.live_verify import redact

OUT = ROOT / "evals/results/compose-acceptance.json"
ARTIFACTS = ROOT / "evals/results"


def tcp_port(value):
    port = int(value)
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be between 1 and 65535.")
    return port


def child_environment(args, source=None):
    """Pass the same isolated target into Compose, smoke and both browsers."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", args.project):
        raise ValueError("Compose project must use lowercase letters, digits, '_' or '-'.")
    if len({args.app_port, args.redis_port, args.browser_port}) != 3:
        raise ValueError("App, Redis and Browser ports must be distinct.")
    env = dict(os.environ if source is None else source)
    base = f"http://127.0.0.1:{args.app_port}"
    env.update(COMPOSE_PROJECT_NAME=args.project, RS_APP_PORT=str(args.app_port), RS_REDIS_PORT=str(args.redis_port), RS_BROWSER_PORT=str(args.browser_port), RS_ACTUAL_BASE=base, RS_UI_BASE=base, PYTHONUNBUFFERED="1")
    # A prior local Playwright install can be reused without another download.
    if not env.get("PLAYWRIGHT_BROWSERS_PATH") and Path("/tmp/ringsight-browsers").is_dir():
        env["PLAYWRIGHT_BROWSERS_PATH"] = "/tmp/ringsight-browsers"
    return env


def fresh_pass(path, started_ns):
    if not path.exists() or path.stat().st_mtime_ns < started_ns:
        raise AssertionError("The child did not write a fresh result: " + path.name)
    data = json.loads(path.read_text())
    if data.get("status") != "passed":
        raise AssertionError("The child did not record a pass: " + path.name)
    return {"path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "status": "passed"}


def run_command(command, env, timeout=2400):
    """Stream useful progress while redacting any inherited credentials."""
    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
    expired = threading.Event()
    def stop():
        expired.set()
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    timer = threading.Timer(timeout, stop)
    timer.daemon = True
    timer.start()
    try:
        for line in process.stdout:
            print(redact(line.rstrip("\n")), flush=True)
        code = process.wait()
        if expired.is_set():
            raise TimeoutError("The verification step exceeded its deadline.")
        if code:
            raise RuntimeError("Verification command exited with code " + str(code))
    finally:
        timer.cancel()
        process.stdout.close()


def main(args):
    load_dotenv(ROOT / ".env", override=True)
    env = child_environment(args)
    missing = [name for name in ("docker", "make", "uv") if not shutil.which(name)]
    if missing:
        raise SystemExit("Required local tools are missing: " + ", ".join(missing))
    report = {"suite": "isolated-compose-acceptance", "status": "running", "started_at": int(time.time()), "project": args.project, "target": env["RS_ACTUAL_BASE"], "ports": {"app": args.app_port, "redis": args.redis_port, "browser": args.browser_port}, "dockerfile": "Dockerfile", "investigation_requests": 0, "health_probe_note": "The actual UI can cause the existing cached readiness probe; no investigation model is requested.", "steps": []}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    def save():
        OUT.write_text(json.dumps(redact(report), indent=2) + "\n")
    save()
    def step(name, command, artifact=None, timeout=2400):
        print(name + "…", flush=True)
        started_ns = time.time_ns()
        item = {"name": name, "command": command, "status": "running", "started_at": started_ns / 1e9}
        report["steps"].append(item)
        save()
        try:
            run_command(command, env, timeout=timeout)
            if artifact:
                item["artifact"] = fresh_pass(artifact, started_ns)
            item["status"] = "passed"
        except Exception as exc:
            item.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
            raise
        finally:
            item["elapsed_s"] = round((time.time_ns() - started_ns) / 1e9, 3)
            save()
    try:
        volume = subprocess.run(["docker", "volume", "inspect", args.project + "_falkordb_data"], cwd=ROOT, env=env, capture_output=True, timeout=20)
        if volume.returncode and b"no such volume" not in volume.stderr.lower() and b"does not exist" not in volume.stderr.lower():
            raise RuntimeError("Could not inspect the acceptance volume; check Docker is running.")
        report["volume_existed_before_run"] = volume.returncode == 0
        report["fresh_volume_note"] = "Existing acceptance volume retained; this proves rebuild/start/persistence, not an empty-volume start." if volume.returncode == 0 else "The isolated acceptance volume did not exist before this run."
        save()
        step("Build and start isolated Compose; prove AOF persistence", ["make", "smoke"], ARTIFACTS / "local-smoke.json")
        images = subprocess.run(["docker", "compose", "images", "--quiet", "app"], cwd=ROOT, env=env, capture_output=True, timeout=30, check=True)
        image_ids = images.stdout.decode().strip().splitlines()
        if len(image_ids) != 1:
            raise AssertionError("Expected the single app image built for this Compose project.")
        image = subprocess.run(["docker", "image", "inspect", "--format", "{{.Id}} {{.Architecture}}", image_ids[0]], cwd=ROOT, env=env, capture_output=True, timeout=30, check=True)
        identifier, architecture = image.stdout.decode().strip().split()
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", identifier):
            raise AssertionError("Docker did not return a verifiable app image digest.")
        report["built_app_image"] = {"id": identifier, "architecture": architecture, "dockerfile_sha256": hashlib.sha256((ROOT / "Dockerfile").read_bytes()).hexdigest(), "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(), "frontend_lock_sha256": hashlib.sha256((ROOT / "ui/package-lock.json").read_bytes()).hexdigest()}
        save()
        # Read the package's expected executable path in a child with the same
        # browser-cache environment. No browser page or model call is opened.
        path = subprocess.run([sys.executable, "-c", "from pathlib import Path; from playwright.sync_api import sync_playwright; p=sync_playwright().start(); ok=Path(p.chromium.executable_path).is_file(); p.stop(); raise SystemExit(0 if ok else 1)"], cwd=ROOT, env=env, capture_output=True, timeout=30)
        if path.returncode:
            step("Install the pinned Playwright Chromium runtime", [sys.executable, "-m", "playwright", "install", "chromium"], timeout=600)
        step("Actual headless browser against the built app and graph", [sys.executable, "ops/ui_actual.py", "--url", env["RS_ACTUAL_BASE"]], ARTIFACTS / "ui-real-local.json", timeout=180)
        step("Frontend interaction contracts against built assets (API fixtures)", [sys.executable, "ops/ui_browser.py"], ARTIFACTS / "ui-browser.json", timeout=180)
        report.update(status="passed", finished_at=int(time.time()))
        print(json.dumps({"status": "passed", "project": args.project, "url": env["RS_ACTUAL_BASE"], "result": str(OUT.relative_to(ROOT))}), flush=True)
    except Exception as exc:
        report.update(status="failed", finished_at=int(time.time()), error={"type": type(exc).__name__, "message": str(exc)})
        raise SystemExit("Isolated Compose verification failed; see evals/results/compose-acceptance.json.") from None
    finally:
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default="rs_acceptance", help="Isolated Compose project; existing volumes are retained.")
    parser.add_argument("--app-port", type=tcp_port, default=18000)
    parser.add_argument("--redis-port", type=tcp_port, default=16379)
    parser.add_argument("--browser-port", type=tcp_port, default=13000)
    main(parser.parse_args())
