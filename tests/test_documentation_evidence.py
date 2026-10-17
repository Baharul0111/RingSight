"""Documentation must distinguish actual measurements, configuration and stale proof."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from ops import collect_workflow_evidence as collector
from ops.workflow_evidence import REPOSITORY, WORKFLOWS, commit_matches_sources, validate_workflow_evidence, workflow_source_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def run_metadata(name, head="a" * 40, *, conclusion="success"):
    run_id = WORKFLOWS.index(name) + 1
    return {"databaseId": run_id, "headSha": head, "status": "completed", "conclusion": conclusion,
            "url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}"}


def current_evidence(root):
    fingerprint = workflow_source_fingerprint(root)
    return {"status": "passed", "repository": REPOSITORY, "head_sha": "a" * 40,
            "source_fingerprint": fingerprint,
            "workflows": {name: {**run_metadata(name), "source_fingerprint": fingerprint} for name in WORKFLOWS}}


def test_operational_evidence_rejects_failure_wrong_commit_or_another_repository(tmp_path):
    value = current_evidence(tmp_path)
    validate_workflow_evidence(value, tmp_path)
    for mutation in (
        lambda v: v.update(repository="another/repository"),
        lambda v: v["workflows"]["daily-probe.yml"].update(conclusion="failure"),
        lambda v: v["workflows"]["keepalive.yml"].update(source_fingerprint="different"),
        lambda v: v["workflows"]["ci.yml"].update(status="in_progress"),
        lambda v: v["workflows"]["ci.yml"].update(url="https://example.org/run"),
    ):
        changed = copy.deepcopy(value)
        mutation(changed)
        with pytest.raises(AssertionError):
            validate_workflow_evidence(changed, tmp_path)


def test_evidence_commit_does_not_invalidate_jobs_but_runtime_edit_does(tmp_path):
    source = tmp_path / "server/app.py"
    source.parent.mkdir()
    source.write_text("original = True\n")
    value = current_evidence(tmp_path)
    (tmp_path / "README.md").write_text("Final measured documentation\n")
    (tmp_path / "evals/results").mkdir(parents=True)
    (tmp_path / "evals/results/operational-probes.json").write_text(json.dumps(value))
    validate_workflow_evidence(value, tmp_path)
    source.write_text("changed = True\n")
    with pytest.raises(AssertionError, match="predate"):
        validate_workflow_evidence(value, tmp_path)


def test_collector_records_actual_commands_and_never_chooses_old_success_over_new_failure(tmp_path, monkeypatch):
    calls = []
    def command(arguments, *, cwd):
        calls.append(arguments)
        if arguments[:3] == ["git", "status", "--porcelain"]:
            return ""
        if arguments == ["git", "rev-parse", "HEAD"]:
            return "a" * 40 + "\n"
        name = arguments[arguments.index("--workflow") + 1]
        assert arguments[:3] == ["gh", "run", "list"]
        assert "--branch" in arguments and arguments[arguments.index("--branch") + 1] == "main"
        newest = run_metadata(name, conclusion="failure" if name == "daily-probe.yml" else "success")
        return json.dumps([newest, run_metadata(name)])
    monkeypatch.setattr(collector, "command", command)
    monkeypatch.setattr(collector, "commit_matches_sources", lambda root, commit: True)
    result = collector.collect(tmp_path)
    assert result["status"] == "failed"
    assert "daily-probe.yml" in result["error"]
    assert all(not any(part in {"workflow", "secret", "dispatch"} for part in call[:3]) for call in calls)


def test_collector_refuses_dirty_source_before_any_github_request(tmp_path, monkeypatch):
    calls = []
    def command(arguments, *, cwd):
        calls.append(arguments)
        return " M server/app.py\n"
    monkeypatch.setattr(collector, "command", command)
    result = collector.collect(tmp_path)
    assert result["status"] == "failed" and "Commit and push" in result["error"]
    assert len(calls) == 1 and calls[0][0] == "git"


def test_collector_accepts_earlier_source_equivalent_runs_after_evidence_commit(tmp_path, monkeypatch):
    def command(arguments, *, cwd):
        if arguments[:3] == ["git", "status", "--porcelain"]:
            return ""
        if arguments == ["git", "rev-parse", "HEAD"]:
            return "b" * 40 + "\n"
        name = arguments[arguments.index("--workflow") + 1]
        pending = {**run_metadata(name, head="b" * 40), "status": "in_progress", "conclusion": None}
        return json.dumps([pending, run_metadata(name)])
    monkeypatch.setattr(collector, "command", command)
    monkeypatch.setattr(collector, "commit_matches_sources", lambda root, commit: commit in {"a" * 40, "b" * 40})
    value = collector.collect(tmp_path)
    assert value["status"] == "passed" and value["head_sha"] == "b" * 40
    assert all(run["headSha"] == "a" * 40 for run in value["workflows"].values())
    validate_workflow_evidence(value, tmp_path)


def test_source_commit_comparison_catches_changed_or_deleted_code_without_checkout(tmp_path):
    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()
    git("init", "--quiet")
    source = tmp_path / "server/app.py"
    source.parent.mkdir()
    source.write_text("original = True\n")
    git("add", "server/app.py")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "Source")
    original = git("rev-parse", "HEAD")
    (tmp_path / "README.md").write_text("Measured final documentation\n")
    git("add", "README.md")
    git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "--quiet", "-m", "Evidence only")
    assert commit_matches_sources(tmp_path, original)
    source.write_text("changed = True\n")
    assert not commit_matches_sources(tmp_path, original)
    source.unlink()
    assert not commit_matches_sources(tmp_path, original)


def build_readme(root, *, canonical_status="passed"):
    for folder in ("scripts", "ops", "server", "evals/results"):
        (root / folder).mkdir(parents=True)
    shutil.copy2(ROOT / "scripts/build_readme.py", root / "scripts/build_readme.py")
    shutil.copy2(ROOT / "ops/workflow_evidence.py", root / "ops/workflow_evidence.py")
    (root / "server/__init__.py").write_text("")
    (root / "server/schemas.py").write_text("INPUT_MODELS = {}\n")
    (root / "server/mcp_read.py").write_text("_DESCRIPTIONS = {}\n")
    results = root / "evals/results"
    (results / "live-five_concurrent.json").write_text(json.dumps({"status": canonical_status,
        "latency": {"depth_4": {"n": 3, "p50_s": 11, "p95_s": 19}}}))
    (results / "live-load.json").write_text(json.dumps({"status": "passed",
        "latency": {"depth_4": {"n": 3, "p50_s": 90, "p95_s": 99}}}))
    (results / "operations.json").write_text(json.dumps({
        "uptimerobot_monitor_enabled": True, "cloudflare_cron_enabled": True,
        "github_keepalive_workflow_present": True}))
    (results / "pytest.json").write_text(json.dumps({"exitcode": 1,
        "summary": {"passed": 2, "error": 1, "skipped": 1}}))
    subprocess.run([sys.executable, str(root / "scripts/build_readme.py")], cwd=root,
                   capture_output=True, check=True, timeout=15)
    return (root / "README.md").read_text()


def test_readme_uses_actual_load_filename_and_distinguishes_monitor_setup_from_execution(tmp_path):
    text = build_readme(tmp_path)
    assert "| Live concurrent load | 4 | 3 | 11.000 | 19.000 |" in text
    assert "| 90.000 | 99.000 |" not in text
    assert "owner confirmed UptimeRobot" in text
    assert "does not establish a successful job or email delivery" in text
    assert "2 passed; 0 failed; 1 error; 1 skipped; exit 1" in text


def test_failed_canonical_load_does_not_fall_back_to_a_stale_success(tmp_path):
    text = build_readme(tmp_path, canonical_status="failed")
    assert "| Live concurrent load |" not in text
