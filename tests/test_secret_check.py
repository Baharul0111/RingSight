"""Use temporary fake values only; never load the workspace's live credentials."""
import base64
import json
from pathlib import Path
from urllib.parse import quote

import pytest

from scripts import check_secrets as checker


def fake_secrets():
    return [checker.Secret('ANTHROPIC_API_KEY', 'sk-' + 'ant-api03-' + 'unit-test-value-' * 3),
            checker.Secret('REDIS_URL', 'redis://user:fake-unit-password@localhost:6379'),
            checker.Secret('FALKORDB_PASSWORD', 'fake/unit+password!'),
            checker.Secret('PO_DEMO_KEY', 'fake-officer-token-0123456789'),
            checker.Secret('ADMIN_TOKEN', 'fake-admin-token-0123456789'),
            checker.Secret('JUDGE_KEY', 'fake-judge-token-0123456789', True),
            checker.Secret('MCP_READ_TOKEN', 'fake-mcp-token-0123456789', True)]


@pytest.mark.parametrize('secret', fake_secrets(), ids=lambda secret:secret.name)
@pytest.mark.parametrize('path', ['server/config.py','ui/src/App.jsx','ui/dist/assets/app.js'])
def test_keys_are_blocked_in_code_and_ui_without_echoing_values(secret, path):
    violations = checker.scan_content(path, secret.value.encode(), [secret])
    assert any(item['secret']==secret.name for item in violations)
    assert secret.value not in json.dumps(violations)


def test_only_public_judge_and_mcp_values_are_allowed_in_root_readme():
    secrets = fake_secrets()
    for secret in secrets:
        hits = checker.scan_content('README.md', secret.value.encode(), [secret])
        assert bool(hits) is not secret.public_in_readme
    for secret in secrets[-2:]:
        assert checker.scan_content('docs/README.md',secret.value.encode(),[secret])
        assert checker.scan_content('ui/dist/README.md',secret.value.encode(),[secret],source='ui_build')


def test_encoded_values_and_filename_values_are_detected_and_redacted():
    secret = fake_secrets()[2]
    for value in [quote(secret.value,safe='').encode(),base64.b64encode(secret.value.encode())]:
        hits = checker.scan_content('docs/output.txt',value,[secret])
        assert hits and secret.value not in json.dumps(hits)
    hits = checker.scan_content('docs/'+secret.value.replace('/','-')+'.txt',b'', [secret])
    assert hits == []  # Different literal bytes are not the secret.
    secret = fake_secrets()[4]
    hits = checker.scan_content('docs/'+secret.value+'.txt',b'', [secret])
    assert hits and secret.value not in json.dumps(hits)


@pytest.mark.parametrize('path', ['.env','.env.production','.aws/credentials','.ssh/id_ed25519',
                                 'ops/private.pem','credentials.json','artifacts/private/trace.json'])
def test_private_paths_fail_even_without_a_secret_value_match(path):
    assert any(item['code']=='private_file' for item in checker.scan_content(path,b'placeholder',[]))
    assert checker.scan_content('.env.example',b'ADMIN_TOKEN=replace-me',[]) == []


def test_generic_credentials_are_caught_and_templated_urls_are_allowed():
    key = ('sk-'+'ant-api03-'+('x'*40)).encode()
    for data in [key,b'-----BEGIN '+b'PRIVATE KEY-----',b'redis://default:'+b'unknown-real-password@localhost:6379']:
        hits = checker.scan_content('output.log',data,[])
        assert hits and data.decode() not in json.dumps(hits)
    assert checker.scan_content('.env.example',b'REDIS_URL=redis://default:REPLACE_PASSWORD@localhost:6379',[]) == []
    assert checker.scan_content('docker-compose.yml',b'redis://default:${FALKORDB_PASSWORD}@falkordb:6379',[]) == []


def test_dotenv_read_does_not_change_process_environment_or_echo_values(tmp_path,monkeypatch):
    value = 'fake/encoded+password!'
    monkeypatch.delenv('FALKORDB_PASSWORD',raising=False)
    path = tmp_path/'.env'
    path.write_text('FALKORDB_PASSWORD='+value+'\nREDIS_URL=redis://default:'+quote(value,safe='')+'@localhost:6379\n',encoding='utf-8')
    secrets = checker.load_secrets(path)
    assert any(secret.name=='REDIS_URL_PASSWORD' and secret.value==value for secret in secrets)
    assert 'FALKORDB_PASSWORD' not in checker.os.environ
    assert checker.scan_content('server.py',value.encode(),secrets)


def make_fake_repository(tmp_path,monkeypatch):
    secrets = fake_secrets()
    (tmp_path/'.env').write_text('\n'.join(secret.name+'='+secret.value for secret in secrets)+'\n',encoding='utf-8')
    (tmp_path/'README.md').write_text(secrets[-2].value+'\n'+secrets[-1].value,encoding='utf-8')
    (tmp_path/'server.py').write_text('print("synthetic demo")',encoding='utf-8')
    (tmp_path/'artifacts/private').mkdir(parents=True)
    (tmp_path/'artifacts/private/ignored.txt').write_text(secrets[0].value,encoding='utf-8')
    monkeypatch.setattr(checker,'git_candidates',lambda root:(['README.md','server.py'],['README.md']))
    monkeypatch.setattr(checker,'_git',lambda root,*args:(tmp_path/'README.md').read_bytes())
    return secrets


def test_candidate_scan_obeys_git_exclusions_and_checks_ignored_ui(tmp_path,monkeypatch):
    secrets = make_fake_repository(tmp_path,monkeypatch)
    report = checker.check_repository(tmp_path)
    assert report['status']=='passed' and report['files_checked']==3
    ui = tmp_path/'ui/dist/assets'
    ui.mkdir(parents=True)
    (ui/'app.js').write_text(secrets[-2].value,encoding='utf-8')
    report = checker.check_repository(tmp_path)
    assert report['status']=='failed' and report['built_ui_checked']
    assert any(item['source']=='ui_build' and item['secret']=='JUDGE_KEY' for item in report['violations'])
    assert all(secret.value not in json.dumps(report) for secret in secrets)


def test_staged_content_is_scanned_even_after_working_file_is_clean(tmp_path,monkeypatch):
    secrets = make_fake_repository(tmp_path,monkeypatch)
    monkeypatch.setattr(checker,'_git',lambda root,*args:secrets[0].value.encode())
    report = checker.check_repository(tmp_path)
    assert report['status']=='failed'
    assert any(item['source']=='git_index' and item['secret']=='ANTHROPIC_API_KEY' for item in report['violations'])


def test_tracked_dotenv_fails_and_cli_output_never_contains_values(tmp_path,monkeypatch,capsys):
    secrets = make_fake_repository(tmp_path,monkeypatch)
    monkeypatch.setattr(checker,'git_candidates',lambda root:(['.env'],['.env']))
    monkeypatch.setattr(checker,'_git',lambda root,*args:(tmp_path/'.env').read_bytes())
    assert checker.main(['--root',str(tmp_path)])==1
    output = capsys.readouterr().out
    assert 'private_file' in output and '.env' in output
    assert all(secret.value not in output for secret in secrets)


def test_unavailable_environment_fails_without_printing_path_or_exception(tmp_path,capsys):
    assert checker.main(['--root',str(tmp_path)])==2
    output = capsys.readouterr().out
    assert 'missing' in output and str(tmp_path) not in output
