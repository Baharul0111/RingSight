"""Offline catalogue identity and session audit regressions (no model or DB)."""
import copy
import hashlib
import uuid

import pytest
from fastmcp import Client

from server import catalogue
from server.context import Identity, Investigation


def test_private_validation_schema_changes_invalidate_catalogue():
    schemas = catalogue._tool_schemas()
    assert len(schemas) == 16
    assert schemas['rs_propose_action']['properties']['rationale']['minLength'] == 80
    assert schemas['rs_record_finding']['properties']['text']['maxLength'] == 1200
    original = catalogue._fingerprint(schemas, 'prompt', {'read.cypher': 'RETURN 1'}, {})
    changed = copy.deepcopy(schemas)
    changed['rs_propose_action']['properties']['rationale']['minLength'] = 81
    revision = catalogue._fingerprint(changed, 'prompt', {'read.cypher': 'RETURN 1'}, {})
    assert revision['schemas_sha256'] != original['schemas_sha256']
    assert revision['hash'] != original['hash']
    assert revision['prompt_sha256'] == original['prompt_sha256']


def test_prompt_query_and_inline_implementation_changes_invalidate_catalogue():
    schemas = catalogue._tool_schemas()
    original = catalogue._fingerprint(schemas, 'prompt', {'read.cypher': 'RETURN 1'}, {'write.py': 'old'})
    for prompt, queries, implementations in [
        ('different prompt', {'read.cypher': 'RETURN 1'}, {'write.py': 'old'}),
        ('prompt', {'read.cypher': 'RETURN 2'}, {'write.py': 'old'}),
        ('prompt', {'renamed.cypher': 'RETURN 1'}, {'write.py': 'old'}),
        ('prompt', {'read.cypher': 'RETURN 1'}, {'write.py': 'new'}),
    ]:
        assert catalogue._fingerprint(schemas, prompt, queries, implementations)['hash'] != original['hash']
    # A different map insertion order is not a different catalogue.
    reordered = dict(reversed(list(schemas.items())))
    assert catalogue._fingerprint(reordered, 'prompt', {'read.cypher': 'RETURN 1'}, {'write.py': 'old'}) == original


def test_hash_is_independent_of_working_directory_and_rejects_extra_tool(monkeypatch, tmp_path):
    original = catalogue.catalogue_metadata()
    monkeypatch.chdir(tmp_path)
    assert catalogue.catalogue_metadata() == original
    schemas = catalogue._tool_schemas() | {'run_cypher': {'type': 'object'}}
    with pytest.raises(ValueError, match='exactly the frozen sixteen'):
        catalogue._fingerprint(schemas, 'prompt', {}, {})


@pytest.mark.parametrize('component',['verifier.py','safety.py','actions.py','auth.py','db.py','context.py'])
def test_policy_and_persistence_source_changes_invalidate_evaluation_identity(monkeypatch,tmp_path,component):
    import shutil
    source=catalogue.SERVER_DIRECTORY
    for path in source.glob('*.py'):shutil.copyfile(path,tmp_path/path.name)
    shutil.copytree(source/'cypher',tmp_path/'cypher')
    monkeypatch.setattr(catalogue,'SERVER_DIRECTORY',tmp_path)
    before=catalogue.catalogue_metadata()
    changed=tmp_path/component
    changed.write_text(changed.read_text()+'\n# A reviewed policy revision.\n')
    after=catalogue.catalogue_metadata()
    assert after['hash']!=before['hash']
    assert after['implementation_sha256']!=before['implementation_sha256']
    assert after['prompt_sha256']==before['prompt_sha256']


def test_prompt_digest_is_the_actual_planner_text_and_does_not_execute_source(tmp_path):
    from server.agent import SYSTEM
    assert catalogue._planner_prompt() == SYSTEM
    assert catalogue.catalogue_metadata()['prompt_sha256'] == hashlib.sha256(SYSTEM.encode('utf-8')).hexdigest()
    (tmp_path / 'agent.py').write_text("SYSTEM = dangerous_function()\n", encoding='utf-8')
    with pytest.raises(ValueError):
        catalogue._planner_prompt(tmp_path)


async def test_exact_fourteen_public_reads_and_two_private_writes_match_fingerprint():
    from server.mcp_read import read_srv
    from server.mcp_write import write_srv
    async with Client(read_srv) as client:
        reads = await client.list_tools()
    async with Client(write_srv) as client:
        writes = await client.list_tools()
    assert len(reads) == 14 and len(writes) == 2
    assert {tool.name for tool in reads} == set(catalogue.FROZEN_TOOLS[:14])
    assert {tool.name for tool in writes} == set(catalogue.FROZEN_TOOLS[14:])
    assert all(tool.annotations.read_only_hint for tool in reads)
    assert all(tool.annotations.read_only_hint is False for tool in writes)
    assert set(catalogue._tool_schemas()) == {tool.name for tool in reads + writes}


async def test_session_stamps_server_identity_and_complete_catalogue_version(monkeypatch):
    from server.actions import create_session
    from server.config import settings
    from server.db import db
    calls = []

    async def write(tenant, query, params):
        calls.append((tenant, query, params))
        return [{'id': params['id']}]

    monkeypatch.setattr(db, 'write', write)
    ctx = Investigation(Identity('named-reviewer', 'analyst', 'audit_bank'), as_of=12345)
    session_id = await create_session(ctx)
    assert uuid.UUID(session_id).version == 4
    tenant, query, params = calls[0]
    assert tenant == params['tenant'] == 'audit_bank'
    assert params['analyst'] == 'named-reviewer' and params['asof'] == 12345
    assert params['model'] == settings.planner and params['judge'] == settings.judge
    version = catalogue.catalogue_metadata()
    for parameter, field in [('hash', 'hash'), ('tools', 'tools'), ('prompt', 'prompt_sha256'),
                             ('schemas', 'schemas_sha256'), ('cypher', 'cypher_sha256'),
                             ('implementation', 'implementation_sha256'), ('format', 'format')]:
        assert params[parameter] == version[field]
    assert 'catalogue_hash:$hash,prompt_sha256:$prompt' in query
    assert 'MERGE (c:CatalogueVersion {hash:$hash}) ON CREATE SET' in query
    assert 'c.prompt_sha256=$prompt' in query and 'c.schemas_sha256=$schemas' in query
    assert 'MERGE (s)-[:USED]->(c)' in query
