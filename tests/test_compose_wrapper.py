"""The one-command wrapper must export one target and reject stale evidence."""
import json
import os
from types import SimpleNamespace
import time

import pytest

from ops.verify_compose import child_environment, fresh_pass


def arguments(**changes):
    return SimpleNamespace(**({"project": "rs_acceptance", "app_port": 18000, "redis_port": 16379, "browser_port": 13000} | changes))


def test_every_compose_and_browser_child_gets_explicit_same_isolated_target():
    env = child_environment(arguments(), {"RS_APP_PORT": "8000", "RS_REDIS_PORT": "6379", "COMPOSE_PROJECT_NAME": "unrelated", "REDIS_URL": "redis://private-test-fixture", "UNCHANGED_FIXTURE": "retained"})
    assert {key: env[key] for key in ("COMPOSE_PROJECT_NAME", "RS_APP_PORT", "RS_REDIS_PORT", "RS_BROWSER_PORT")} == {"COMPOSE_PROJECT_NAME": "rs_acceptance", "RS_APP_PORT": "18000", "RS_REDIS_PORT": "16379", "RS_BROWSER_PORT": "13000"}
    assert env["RS_ACTUAL_BASE"] == env["RS_UI_BASE"] == "http://127.0.0.1:18000"
    assert env["REDIS_URL"] == "redis://private-test-fixture"
    assert env["UNCHANGED_FIXTURE"] == "retained"


def test_completed_child_cannot_pass_using_earlier_success_file(tmp_path):
    result = tmp_path / "child.json"
    result.write_text(json.dumps({"status": "passed"}))
    old_ns = time.time_ns() - 5_000_000_000
    os.utime(result, ns=(old_ns, old_ns))
    with pytest.raises(AssertionError, match="fresh result"):
        fresh_pass(result, time.time_ns())
    started = time.time_ns()
    result.write_text(json.dumps({"status": "running"}))
    with pytest.raises(AssertionError, match="record a pass"):
        fresh_pass(result, started)
    result.write_text(json.dumps({"status": "passed"}))
    assert fresh_pass(result, started)["status"] == "passed"


@pytest.mark.parametrize("changes", [{"project": "bad;project"}, {"project": "../other-project"}, {"app_port": 16379}])
def test_wrapper_rejects_unsafe_project_or_colliding_ports(changes):
    with pytest.raises(ValueError):
        child_environment(arguments(**changes), {})
