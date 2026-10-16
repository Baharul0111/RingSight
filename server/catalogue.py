import hashlib
import json
from pathlib import Path

def tool_names():
    from server.mcp_read import TOOL_SCHEMAS
    return sorted(TOOL_SCHEMAS)+['rs_record_finding','rs_propose_action']
def catalogue_hash():
    from server.mcp_read import TOOL_SCHEMAS
    schemas={n:(s.model_json_schema() if hasattr(s,'model_json_schema') else s) for n,s in TOOL_SCHEMAS.items()}
    digest=json.dumps(schemas,sort_keys=True,default=str).encode()
    for p in sorted(Path('server/cypher').glob('*.cypher')):digest+=p.read_bytes()
    return hashlib.sha256(digest).hexdigest()
