"""Deterministic evidence verifier. Text cannot add identifiers, currency or dates."""
import datetime as dt
import re
from decimal import Decimal
from typing import Any
ID_RE=re.compile(r'\b(?:ACC|PER|DEV|PH|PHONE|ADR|ADDR|MER|TX|AL|RES)-[A-Za-z0-9]+\b',re.I)
MONEY_RE=re.compile(r'(?:₹|INR\s*|Rs\.?\s*)([\d,]+(?:\.\d+)?)\s*(lakh|lac|crore|cr|k|million)?',re.I)
DATE_RE=re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
AMOUNT_KEYS={'amount','total','in_sum','out_sum','drain_sum','scattered','gathered','internal_amount','out_amt','in_amt','in_max','amount_after_closure_request','capacity','flow'}
IST=dt.timezone(dt.timedelta(hours=5,minutes=30))
def flatten(value:Any):
    if isinstance(value,dict):
        for key,item in value.items():
            yield key,item
            yield from flatten(item)
    elif isinstance(value,(list,tuple)):
        for item in value:yield from flatten(item)

def evidence_sets(calls):
    ids=set(); amounts=set(); dates=set(); numbers=set()
    for call in (calls.values() if isinstance(calls,dict) else calls):
        rows=call.get('rows',[])
        ids.update(ID_RE.findall(str(rows)))
        for key,value in flatten(rows):
            if isinstance(value,(int,float)) and not isinstance(value,bool):
                numbers.add(value)
                if key in AMOUNT_KEYS or key.endswith('_amount'):amounts.add(value)
                if (key in {'ts','created_at','date_learned','valid_from','valid_to','first_ts','last_ts','first','last','in_force_from'} or key.endswith('_ts')) and 1000000000<value<4102444800:
                    dates.add(dt.datetime.fromtimestamp(value,IST).date().isoformat())
                    dates.add(dt.datetime.fromtimestamp(value,dt.timezone.utc).date().isoformat())
            elif isinstance(value,str):dates.update(DATE_RE.findall(value))
    return ids,amounts,dates,numbers

def parse_amount(number,suffix=None):
    multiplier={'lakh':100000,'lac':100000,'crore':10000000,'cr':10000000,'k':1000,'million':1000000}.get((suffix or '').lower(),1)
    return int(Decimal(number.replace(',',''))*multiplier*100)

def verify(text,calls,shape=None,cited_ids=None):
    selected={k:v for k,v in calls.items() if not cited_ids or k in cited_ids} if isinstance(calls,dict) else calls
    ids,amounts,dates,numbers=evidence_sets(selected)
    unsupported=[]
    for identifier in ID_RE.findall(text):
        if identifier not in ids:unsupported.append(identifier)
    normalizations=[]
    for match in MONEY_RE.finditer(text):
        paise=parse_amount(*match.groups()); normalizations.append({'text':match.group(0),'paise':paise})
        if not any(abs(paise-x)<=max(1,abs(x)*.01) for x in amounts):unsupported.append(match.group(0))
    for date in DATE_RE.findall(text):
        if date not in dates:unsupported.append(date)
    rows=list(selected.values()) if isinstance(selected,dict) else list(selected)
    if shape=='answered_with_path' and not any(c.get('path_nodes') and c.get('rows_total',0)>0 for c in rows):unsupported.append('shape_requires_path')
    if shape=='answered_from_memory' and not any(c.get('outcome')=='answered_from_memory' and c.get('rows_total',0)>0 for c in rows):unsupported.append('shape_requires_memory')
    return {'status':'replaced' if unsupported else 'pass','unsupported':unsupported,'normalizations':normalizations}

def template_answer(calls):
    usable=[c for c in calls.values() if c.get('outcome')=='answered_with_path' and c.get('path_nodes') and c.get('rows_total',0)>0]
    if usable:
        nodes=usable[-1]['path_nodes']; ids=[n.get('id') if isinstance(n,dict) else str(n) for n in nodes]
        return 'The graph returned this evidence path: '+' → '.join(dict.fromkeys(filter(None,ids)))+'. Review the transfer evidence before deciding.'
    return 'The available graph evidence is insufficient. Not in the graph ≠ nothing wrong.'
