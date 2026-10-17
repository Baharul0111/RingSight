"""Completion must reject missing, stale, failed or unexposed evidence."""
import copy
import json
import os
import time

import pytest

from ops.check_completion import checks_pass, model_pass, pytest_pass, source_files, source_fresh


def test_model_badge_or_short_trial_cannot_substitute_for_complete_evidence():
    value = {"complete": True, "passed": True, "local_only": True, "planned_cases": 2,
             "completed_cases": 2, "signature": {"inputs": {"catalogue_hash": "current"}},
             "cases": [{"case_key": "one", "model_requests": 1}, {"case_key": "two", "model_requests": 1}]}
    assert len(model_pass(value, 2, "current")) == 2
    for mutation in (
        lambda d: d.update(complete=False), lambda d: d.update(passed=False),
        lambda d: d.update(local_only=False), lambda d: d.update(planned_cases=1),
        lambda d: d["cases"][1].update(case_key="one"),
        lambda d: d["cases"][0].update(model_requests=0),
        lambda d: d["signature"]["inputs"].update(catalogue_hash="old"),
    ):
        changed = copy.deepcopy(value)
        mutation(changed)
        with pytest.raises(AssertionError):
            model_pass(changed, 2, "current")


def test_workflow_status_does_not_hide_missing_or_failed_required_checks():
    value = {"status": "passed", "checks": {"read": {"status": "passed"}}}
    with pytest.raises(AssertionError, match="approve"):
        checks_pass(value, ["read", "approve"])
    value["checks"]["approve"] = {"status": "failed"}
    with pytest.raises(AssertionError):
        checks_pass(value, ["read", "approve"])


def test_test_exit_zero_cannot_hide_skipped_or_failed_cases():
    with pytest.raises(AssertionError):
        pytest_pass({"exitcode": 0, "summary": {"total": 3, "passed": 2, "skipped": 1}})
    with pytest.raises(AssertionError):
        pytest_pass({"exitcode": 1, "summary": {"total": 2, "passed": 1, "failed": 1}})


def test_current_source_edit_invalidates_older_passing_result(tmp_path):
    folder = tmp_path / "evals/results"
    folder.mkdir(parents=True)
    artifact = folder / "pytest.json"
    artifact.write_text(json.dumps({"exitcode": 0, "summary": {"passed": 1, "total": 1}}))
    old = time.time_ns() - 5_000_000_000
    os.utime(artifact, ns=(old, old))
    source = tmp_path / "changed.py"
    source.write_text("changed = True\n")
    with pytest.raises(AssertionError, match="source/test edit"):
        source_fresh(tmp_path, "pytest.json", [source])


def test_changed_model_harness_invalidates_otherwise_complete_report():
    value = {"complete": True, "passed": True, "local_only": True,
             "planned_cases": 1, "completed_cases": 1,
             "signature": {"inputs": {"catalogue_hash": "current", "harness_sha256": "old"}},
             "cases": [{"case_key": "one", "model_requests": 1}]}
    with pytest.raises(AssertionError, match="evaluation harness"):
        model_pass(value, 1, "current", "new")
    assert model_pass(value, 1, "current", "old") == value["cases"]


def test_test_freshness_includes_ops_and_eval_but_compose_only_needs_image_sources(tmp_path):
    for name in ("ops/proof.py", "evals/model_eval.py", "tests/test_proof.py",
                 "server/app.py", "data/findings_snapshot.json"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}" if path.suffix == ".json" else "x = 1\n")
    all_files = {str(path.relative_to(tmp_path)) for path in source_files(tmp_path)}
    image_files = {str(path.relative_to(tmp_path)) for path in source_files(tmp_path, runtime_only=True)}
    assert all_files == {"ops/proof.py", "evals/model_eval.py", "tests/test_proof.py", "server/app.py", "data/findings_snapshot.json"}
    assert image_files == {"server/app.py", "data/findings_snapshot.json"}
