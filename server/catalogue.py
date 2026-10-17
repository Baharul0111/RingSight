"""Reproducible identity for the sixteen tools and the planner contract.

The input schemas are the complete server-side validation contracts, including
the private writes. Source digests also cover their MCP signatures and inline
Cypher. Named query files are hashed with their boundaries intact. Nothing in
this fingerprint depends on the current directory, environment or credentials.
"""
import ast
import hashlib
import json
from pathlib import Path

SERVER_DIRECTORY = Path(__file__).resolve().parent
FROZEN_TOOLS = (
    'rs_resolve_entity', 'rs_recall_findings', 'rs_account_profile',
    'rs_neighbourhood', 'rs_fan_pattern', 'rs_cycles', 'rs_scatter_gather',
    'rs_path_between', 'rs_ring_members', 'rs_hub_rank', 'rs_money_flow',
    'rs_shared_identifiers', 'rs_check_restrictions', 'rs_coverage_status',
    'rs_record_finding', 'rs_propose_action',
)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _planner_prompt(directory=SERVER_DIRECTORY):
    # Read the literal without importing agent.py: health and session creation
    # must not construct an agent or introduce a circular import. Fail closed if
    # the prompt stops being a literal; its actual bytes must remain auditable.
    source = ast.parse((directory / 'agent.py').read_text(encoding='utf-8'))
    values = [node.value for node in source.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'SYSTEM'
                      for target in node.targets)]
    if len(values) != 1:
        raise ValueError('The planner must define exactly one literal SYSTEM prompt.')
    prompt = ast.literal_eval(values[0])
    if not isinstance(prompt, str) or not prompt:
        raise ValueError('The planner SYSTEM prompt must be a nonempty string.')
    return prompt


def _tool_schemas():
    from server.mcp_read import TOOL_SCHEMAS
    from server.mcp_write import RecordInput, ProposeInput
    schemas = {name: schema for name, schema in TOOL_SCHEMAS.items()}
    schemas.update(rs_record_finding=RecordInput.model_json_schema(),
                   rs_propose_action=ProposeInput.model_json_schema())
    if set(schemas) != set(FROZEN_TOOLS):
        raise ValueError('The tool schemas differ from the frozen sixteen-tool catalogue.')
    return schemas


def _fingerprint(schemas, prompt, queries, implementations):
    """Pure canonical projection, also used to test meaningful change detection."""
    if set(schemas) != set(FROZEN_TOOLS):
        raise ValueError('The fingerprint requires exactly the frozen sixteen tools.')
    components = {
        'format': 2,
        'tools': list(FROZEN_TOOLS),
        'schemas_sha256': _sha256(_canonical(schemas)),
        'prompt_sha256': _sha256(prompt.encode('utf-8')),
        'cypher_sha256': _sha256(_canonical(queries)),
        'implementation_sha256': _sha256(_canonical(implementations)),
    }
    return dict(components, hash=_sha256(_canonical(components)))


def catalogue_metadata():
    queries = {path.name: path.read_text(encoding='utf-8')
               for path in sorted((SERVER_DIRECTORY / 'cypher').glob('*.cypher'))}
    # Both read and write modules contain additional bounded, human-authored
    # statements; hashing only the .cypher files would miss those changes.
    # Verifier, safety, identity and decision code can change a run's meaning
    # just as a query can. Include every server source rather than maintaining
    # an incomplete list that could silently reuse an incompatible evaluation.
    implementations = {path.name: _sha256(path.read_bytes())
                       for path in sorted(SERVER_DIRECTORY.glob('*.py'))}
    return _fingerprint(_tool_schemas(), _planner_prompt(), queries, implementations)


def tool_names():
    return list(FROZEN_TOOLS)


def catalogue_hash():
    return catalogue_metadata()['hash']
