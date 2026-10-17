"""The plain Python runner must explicitly select the safe local database."""
import pytest
from ops.verify_local import local_environment

def test_runner_passes_local_setting_to_child_even_if_shell_only_has_cloud(monkeypatch):
    monkeypatch.delenv('RS_TEST_REDIS_URL',raising=False)
    monkeypatch.setenv('REDIS_URL','redis://cloud.example:6379')
    environment=local_environment('redis://localhost:6380')
    assert environment['RS_TEST_REDIS_URL']=='redis://localhost:6380'
    assert environment['REDIS_URL']=='redis://cloud.example:6379'

@pytest.mark.parametrize('url',['redis://localhost.attacker.example:6379','redis://u:localhost@cloud.example:6379'])
def test_runner_rejects_remote_hosts_even_when_url_contains_localhost(url):
    with pytest.raises(ValueError,match='remote'):local_environment(url)
