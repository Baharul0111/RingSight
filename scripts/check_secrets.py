"""Check public Git candidates and built UI without displaying secret values.

Run ``.venv/bin/python scripts/check_secrets.py --output evals/results/secrets-scan.json``.
The working tree, Git index and ignored ui/dist files are checked. Git's normal
ignore rules exclude untracked private files; an ignored file already tracked
in Git is still checked. This is a pre-push content check, not a history audit.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote, quote_plus, unquote, urlsplit

from dotenv import dotenv_values

PRIVATE_VARIABLES = ('ANTHROPIC_API_KEY', 'REDIS_URL', 'FALKORDB_PASSWORD',
                     'FALKORDB_RO_URL', 'PO_DEMO_KEY', 'ADMIN_TOKEN')
PUBLIC_VARIABLES = ('JUDGE_KEY', 'MCP_READ_TOKEN')
PRIVATE_KEY = re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----')
ANTHROPIC_KEY = re.compile(rb'\bsk-ant-[A-Za-z0-9_-]{20,}')
REDIS_CREDENTIAL = re.compile(rb'\bredis(?:s)?://[^\s\'"<>]+')


@dataclass(frozen=True)
class Secret:
    name: str
    value: str
    public_in_readme: bool = False


class CheckError(Exception):
    """Messages are fixed strings so exception output cannot disclose values."""


def load_secrets(path: Path) -> list[Secret]:
    if not path.is_file():
        raise CheckError('The private .env file is missing; value-based verification cannot run.')
    try:
        values = dotenv_values(path, interpolate=False)
    except Exception:
        raise CheckError('The private environment file could not be read.') from None
    secrets = [Secret(name, values[name], name in PUBLIC_VARIABLES)
               for name in PRIVATE_VARIABLES + PUBLIC_VARIABLES if values.get(name)]
    for name in ('REDIS_URL', 'FALKORDB_RO_URL'):
        if values.get(name):
            try:
                password = urlsplit(values[name]).password
            except ValueError:
                password = None
            if password:
                secrets.append(Secret(name + '_PASSWORD', unquote(password)))
    if values.get('HUMAN_KEYS_JSON'):
        try:
            for key in json.loads(values['HUMAN_KEYS_JSON']):
                if key and key not in {s.value for s in secrets}:
                    secrets.append(Secret('HUMAN_KEYS_JSON_KEY', key))
        except (ValueError, TypeError):
            raise CheckError('HUMAN_KEYS_JSON is malformed; key verification cannot run.') from None
    return secrets


def _variants(value: str) -> set[bytes]:
    encoded = value.encode('utf-8')
    return {encoded, quote(value, safe='').encode(), quote_plus(value).encode(),
            json.dumps(value, ensure_ascii=True)[1:-1].encode(), base64.b64encode(encoded)}


def safe_path(path: str, secrets: list[Secret]) -> str:
    # Even filenames can accidentally contain a key. Do not echo that key in a
    # violation report, and JSON-encode messages at the CLI to escape controls.
    for secret in sorted(secrets, key=lambda item: len(item.value), reverse=True):
        for variant in _variants(secret.value):
            try:path = path.replace(variant.decode('utf-8'), '<redacted:' + secret.name + '>')
            except UnicodeError:pass
    path = ANTHROPIC_KEY.sub(b'<redacted:API_KEY>', path.encode('utf-8')).decode('utf-8')
    return path


def _private_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    parts = tuple(part.lower() for part in path.parts)
    name = path.name.lower()
    return (name == '.env' or (name.startswith('.env.') and name != '.env.example')
            or any(part in {'.aws', '.ssh', '.gnupg'} for part in parts)
            or parts[:2] == ('artifacts', 'private')
            or name in {'credentials', 'credentials.json', 'service-account.json',
                        'id_rsa', 'id_ed25519', 'id_ecdsa', 'id_dsa'}
            or path.suffix.lower() in {'.pem', '.p12', '.pfx', '.key'})


def _placeholder(value: str, hostname: str = '') -> bool:
    value = value.lower()
    hostname = hostname.lower()
    return (value in {'password', 'localhost'}
            or hostname in {'example.com', 'example.org', 'example.net'}
            or hostname.endswith(('.example', '.invalid', '.example.com', '.example.org', '.example.net'))
            or (value.startswith('private-') and value.endswith('-value'))
            or any(marker in value for marker in ('${', '<', '>', 'replace', 'example',
                                                  'fixture', 'fake-', 'unit-test',
                                                  'change-me', 'changeme', 'your_password',
                                                  'your-password', 'your_redis_password')))


def scan_content(relative: str, content: bytes, secrets: list[Secret], source='working_tree') -> list[dict]:
    violations = []
    path = safe_path(relative, secrets)
    def add(code, name):
        item = {'path':path, 'source':source, 'code':code, 'secret':name}
        if item not in violations:violations.append(item)
    if _private_path(relative):
        add('private_file', 'PRIVATE_CREDENTIAL_PATH')
    searchable = os.fsencode(relative) + b'\0' + content
    for secret in secrets:
        if secret.public_in_readme and relative == 'README.md' and source != 'ui_build':
            continue
        if any(variant in searchable for variant in _variants(secret.value)):
            add('exposed_secret', secret.name)
    if PRIVATE_KEY.search(searchable):add('private_key', 'PRIVATE_KEY_MATERIAL')
    if ANTHROPIC_KEY.search(searchable):add('api_key_pattern', 'ANTHROPIC_API_KEY_PATTERN')
    for match in REDIS_CREDENTIAL.finditer(searchable):
        try:
            parsed = urlsplit(match.group().decode('utf-8').rstrip('.,;)'))
            password,hostname = parsed.password,parsed.hostname or ''
        except (ValueError, UnicodeError):
            password,hostname = None,''
        if password and not _placeholder(unquote(password),hostname):
            add('credential_url', 'REDIS_CREDENTIAL_URL')
    return violations


def _git(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(['git', *arguments], cwd=root, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        raise CheckError('Git content discovery could not run.') from None
    if result.returncode:
        raise CheckError('Git content discovery failed; run this command from the repository.')
    return result.stdout


def git_candidates(root: Path) -> tuple[list[str], list[str]]:
    decode = lambda raw: [os.fsdecode(path) for path in raw.split(b'\0') if path]
    tracked = decode(_git(root, 'ls-files', '--cached', '-z'))
    candidates = decode(_git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z'))
    return sorted(set(candidates)), sorted(set(tracked))


def check_repository(root: Path, env_path: Path | None = None) -> dict:
    root = root.resolve()
    secrets = load_secrets(env_path or root / '.env')
    candidates, tracked = git_candidates(root)
    violations = []
    checked = 0
    def check_path(relative, source):
        nonlocal checked
        path = root / relative
        if not path.resolve().is_relative_to(root):
            violations.append({'path':safe_path(relative,secrets), 'source':source,
                               'code':'private_symlink', 'secret':'PRIVATE_SYMLINK_TARGET'})
            checked += 1
            return
        if path.is_symlink():
            target = os.readlink(path)
            violations.extend(scan_content(relative, os.fsencode(target), secrets, source))
            if not path.resolve().is_relative_to(root) or _private_path(target):
                violations.append({'path':safe_path(relative,secrets), 'source':source,
                                   'code':'private_symlink', 'secret':'PRIVATE_SYMLINK_TARGET'})
            checked += 1
        elif path.is_file():
            try:content = path.read_bytes()
            except OSError:raise CheckError('A candidate file could not be read.') from None
            violations.extend(scan_content(relative, content, secrets, source))
            checked += 1
    for relative in candidates:
        check_path(relative, 'working_tree')
    # Staged contents can differ from an edited working file. Check exactly what
    # the next commit would contain as well, without modifying the index.
    for relative in tracked:
        content = _git(root, 'show', ':' + relative)
        violations.extend(scan_content(relative, content, secrets, 'git_index'))
        checked += 1
    ui = root / 'ui' / 'dist'
    if ui.is_symlink():
        check_path('ui/dist', 'ui_build')
    elif ui.is_dir():
        for path in sorted(ui.rglob('*')):
            if path.is_file() or path.is_symlink():
                check_path(path.relative_to(root).as_posix(), 'ui_build')
    # Re-check the report itself before returning it: reporting must never be a
    # second way to expose any of the values being searched for.
    serialized = json.dumps(violations, ensure_ascii=True)
    if any(secret.value in serialized for secret in secrets):
        raise CheckError('A filename could not be safely redacted; no findings were printed.')
    return {'status':'passed' if not violations else 'failed', 'check':'public_candidate_secrets',
            'files_checked':checked, 'candidate_files':len(candidates), 'indexed_files':len(tracked),
            'built_ui_checked':ui.is_dir(), 'violations':violations,
            'scope':['git_working_candidates','git_index','built_ui'], 'history_checked':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        report = check_repository(args.root, args.env_file)
        if args.output:
            output = args.output if args.output.is_absolute() else args.root / args.output
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True))
        return 0 if report['status'] == 'passed' else 1
    except CheckError as error:
        print(json.dumps({'status':'error','error':str(error)}))
        return 2


if __name__ == '__main__':sys.exit(main())
