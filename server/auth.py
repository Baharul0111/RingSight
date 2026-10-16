import hmac
import json
import os
from fastapi import HTTPException
from server.context import Identity

def identify(key:str)->Identity:
    entries=[('JUDGE_KEY',Identity('judge','analyst','bank_a')),('PO_DEMO_KEY',Identity('baharul','principal_officer','bank_a')),('MCP_READ_TOKEN',Identity('mcp','reader','bank_a','mcp')),('ADMIN_TOKEN',Identity('admin','admin','bank_a','admin'))]
    for var,identity in entries:
        candidate=os.getenv(var,'')
        if candidate and hmac.compare_digest(candidate,key):return identity
    for candidate,entry in json.loads(os.getenv('HUMAN_KEYS_JSON','{}')).items():
        if candidate and hmac.compare_digest(candidate,key):return Identity(**entry)
    raise HTTPException(401,detail={'reason':'invalid_key','error':'Enter a valid access key.'})
