"""Save read-only GitHub evidence for current-source CI, health and daily jobs.

Run after pushing source and executing the three workflows:
  .venv/bin/python ops/collect_workflow_evidence.py
This never dispatches a job, calls the model, changes secrets or mutates Git.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops.workflow_evidence import REPOSITORY, WORKFLOWS, commit_matches_sources, validate_workflow_evidence, workflow_source_fingerprint, workflow_sources


def command(arguments, *, cwd):
    process = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, timeout=30)
    if process.returncode:
        # CLI stderr can contain account context; preserve only a safe diagnosis.
        raise RuntimeError(arguments[0] + " failed; check authentication, repository access and workflow history.")
    return process.stdout


def collect(root: Path) -> dict:
    result = {"suite": "operational-workflows", "status": "running", "repository": REPOSITORY,
              "collected_at": int(time.time()), "workflows": {},
              "notes": ["Actual public GitHub run metadata, not owner confirmation.",
                        "No model request or workflow dispatch is made by this collector.",
                        "Each selected run's committed Git blobs must match current relevant sources; documentation/evidence-only commits may differ.",
                        "Successful jobs prove scheduled code execution; they do not independently prove UptimeRobot email delivery."]}
    try:
        sources = [str(path.relative_to(root)) for path in workflow_sources(root)]
        dirty = command(["git", "status", "--porcelain", "--", *sources], cwd=root)
        if dirty.strip():
            raise AssertionError("Commit and push runtime/tests/workflow changes before collecting their successful jobs.")
        head = command(["git", "rev-parse", "HEAD"], cwd=root).strip()
        result.update(head_sha=head, source_fingerprint=workflow_source_fingerprint(root))
        fields = "databaseId,headSha,workflowName,url,conclusion,status,event,createdAt,updatedAt"
        source_matches = {}
        for name in WORKFLOWS:
            runs = json.loads(command(["gh", "run", "list", "--repo", REPOSITORY,
                                       "--workflow", name, "--branch", "main", "--limit", "40",
                                       "--json", fields], cwd=root))
            if not isinstance(runs, list) or not runs:
                raise AssertionError("No run exists for workflow: " + name)
            selected = None
            for run in runs:
                commit = run.get("headSha")
                if commit not in source_matches:
                    source_matches[commit] = commit_matches_sources(root, commit)
                if source_matches[commit] and run.get("status") == "completed":
                    selected = run
                    break
            if selected is None:
                raise AssertionError("No completed recent run matches current committed runtime/tests/workflows: " + name)
            result["workflows"][name] = {key: selected.get(key) for key in fields.split(",")}
            result["workflows"][name]["source_fingerprint"] = result["source_fingerprint"]
        result["status"] = "passed"
        validate_workflow_evidence(result, root)
    except Exception as error:
        result.update(status="failed", error=str(error) if isinstance(error, (AssertionError, RuntimeError)) else type(error).__name__)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evals/results/operational-probes.json")
    options = parser.parse_args()
    result = collect(ROOT)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "error": result.get("error"), "result": str(options.output)}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
