"""Deterministic evidence verifier. Text cannot add identifiers, currency or dates."""
import datetime as dt
import re
from decimal import Decimal,InvalidOperation
from typing import Any
ID_RE=re.compile(r'\b(?:ACC|PER|DEV|PH|PHN|PHONE|ADR|ADDR|ADD|MER|MRC|TX|ALERT|AL|ALT|RES)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*\b',re.I)
MONEY_RE=re.compile(r'(?:₹|\bINR\b\s*|\bRs\.?\s*)([\d,]+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*(lakh|lac|crore|cr|k|million)?',re.I)
CURRENCY_RE=re.compile(r'₹|\bINR\b|\bRs\.?\s*(?=[\d,.])',re.I)
DATE_RE=re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
AMOUNT_KEYS={'amount','total','in_sum','out_sum','drain_sum','scattered','gathered','internal_amount','out_amt','in_amt','in_max','amount_after_closure_request','capacity','flow'}
IST=dt.timezone(dt.timedelta(hours=5,minutes=30))
# Envelopes are pseudonymous: a person or merchant name is never an allowed
# model claim. Unknown capitalised words therefore require the row template,
# including single names which the old multiword-name expression missed.
PROSE_CAPITALS=frozenset('''A An The This These Those It They Their There Both
We Our I No Not Unknown Account Person Device Phone Address Merchant Bank Rail
Graph Evidence Review Human Named Principal Officer Synthetic Unreviewed
Learned Recorded Reviewed Author Based From Between Within At On In As For
To With Without Because Although However Further Shared Multiple Transfers
Funds Transactions Ownership Connected Money Incoming Outgoing Independent
Recommend Recommendation Nothing Returned Available See Before After Link
Connected Observed Directed Escalate Accounts UPI NEFT RTGS IMPS CARD WALLET CASH XB
US IN SAR STR FIU IND FinCEN RBI API MCP UTC IST INR Rs
'''.split())
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
        free_fields={'memo','text','name','name_norm','owner_name','rationale','reason','decision_reason','hint','coverage_warning','banner','projection_note','snapshot_warning','memory_label'}
        def structured(value):
            if isinstance(value,dict):
                return {k:structured(v) for k,v in value.items() if k not in free_fields}
            if isinstance(value,list):return [structured(v) for v in value]
            if isinstance(value,str) and ID_RE.fullmatch(value):ids.add(value)
            return value
        rows=structured(rows)
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
    # Model prose is untrusted. A comma-only token previously reached Decimal
    # as an empty string and aborted the entire paid evaluation. Accept ordinary
    # Western/Indian grouping only, and the graph's signed-64-bit amount range.
    if len(number)>64 or not re.fullmatch(r'(?:\d+|\d{1,3}(?:,\d{3})+|\d{1,2}(?:,\d{2})*,\d{3})(?:\.\d+)?',number):
        raise ValueError('Invalid currency amount')
    multiplier={'lakh':100000,'lac':100000,'crore':10000000,'cr':10000000,'k':1000,'million':1000000}.get((suffix or '').lower(),1)
    try:paise=Decimal(number.replace(',',''))*multiplier*100
    except InvalidOperation:raise ValueError('Invalid currency amount') from None
    if not paise.is_finite() or not 0<=paise<=9223372036854775807:
        raise ValueError('Currency amount exceeds the graph range')
    return int(paise)

def verify(text,calls,shape=None,cited_ids=None):
    selected={k:v for k,v in calls.items() if not cited_ids or k in cited_ids} if isinstance(calls,dict) else calls
    ids,amounts,dates,numbers=evidence_sets(selected)
    unsupported=[]
    for identifier in ID_RE.findall(text):
        if identifier not in ids:unsupported.append(identifier)
    # Remove typed identifiers, currency and dates before checking ordinary
    # quantities (counts, percentages and depths). No ungrounded number is prose.
    remaining=ID_RE.sub('',text)
    remaining=MONEY_RE.sub('',remaining)
    remaining=DATE_RE.sub('',remaining)
    remaining=re.sub(r'[0-9a-f]{8}-[0-9a-f-]{27,}', '', remaining, flags=re.I)
    for token in re.findall(r'(?<![\w-])\d+(?:\.\d+)?(?![\w-])',remaining):
        value=float(token)
        if not any(abs(value-x)<=max(.001,abs(x)*.01) for x in numbers):unsupported.append(token)
    for word in re.findall(r'\b[A-Z][A-Za-z]*\b',remaining):
        if word not in PROSE_CAPITALS:unsupported.append(word)
    normalizations=[]
    money_matches=list(MONEY_RE.finditer(text))
    for marker in CURRENCY_RE.finditer(text):
        if not any(match.start()<=marker.start()<match.end() for match in money_matches):
            unsupported.append('malformed_currency')
    for match in money_matches:
        try:paise=parse_amount(*match.groups())
        except ValueError:
            unsupported.append(match.group(0));continue
        normalizations.append({'text':match.group(0),'paise':paise})
        if not any(abs(paise-x)<=max(1,abs(x)*.01) for x in amounts):unsupported.append(match.group(0))
    for date in DATE_RE.findall(text):
        if date not in dates:unsupported.append(date)
    rows=list(selected.values()) if isinstance(selected,dict) else list(selected)
    if shape=='answered_with_path' and not any(c.get('path_edges') and c.get('rows_total',0)>0 for c in rows):unsupported.append('shape_requires_path')
    if shape=='answered_from_memory' and not any(c.get('outcome')=='answered_from_memory' and c.get('rows_total',0)>0 for c in rows):unsupported.append('shape_requires_memory')
    return {'status':'replaced' if unsupported else 'pass','unsupported':unsupported,'normalizations':normalizations}

def template_answer(calls):
    usable=[c for c in calls.values() if c.get('outcome')=='answered_with_path' and c.get('path_nodes') and c.get('rows_total',0)>0]
    if usable:
        paths=[]
        for call in usable:
            for key,value in flatten(call.get('rows',[])):
                if key in {'path_ids','node_ids','accounts'} and isinstance(value,list) and all(isinstance(x,str) for x in value):paths.append(value)
        if paths:
            path=max(paths,key=len)
            return 'The graph returned this evidence path: '+' → '.join(path)+'. Review the transfer evidence before deciding.'
        ids=[n.get('id') if isinstance(n,dict) else str(n) for n in usable[-1]['path_nodes']]
        return 'The graph returned evidence involving '+', '.join(dict.fromkeys(filter(None,ids)))+'. Review the individual paths and transfer evidence before deciding.'
    return 'The available graph evidence is insufficient. Not in the graph ≠ nothing wrong.'


def validate_transactions(transactions,calls):
    """Require all report facts and match them to one exact evidenced transfer."""
    if not isinstance(transactions,(list,tuple)) or not transactions:return ['transactions_required']
    trusted={}
    def walk(value):
        if isinstance(value,list):
            for item in value:walk(item)
        elif isinstance(value,dict):
            tx=value.get('tx_id') or value.get('tx') or value.get('id')
            if isinstance(tx,str) and tx.startswith('TX-') and 'amount' in value and 'ts' in value:
                trusted[tx]={'amount':value['amount'],'ts':value['ts'],'rail':value.get('rail'),'from_id':value.get('source',value.get('from',value.get('from_id'))),'to_id':value.get('target',value.get('to',value.get('to_id')))}
            for v in value.values():
                if isinstance(v,(dict,list)):walk(v)
    for call in calls.values():
        walk(call.get('rows',[]));walk(call.get('path_edges',[]))
    errors=[]
    for tx in transactions:
        if not isinstance(tx,dict):errors.append('invalid_transaction');continue
        key=tx.get('tx_id',tx.get('id'));evidence=trusted.get(key)
        if not evidence:errors.append(str(key));continue
        for field,aliases in {'amount':['amount'],'ts':['ts'],'rail':['rail'],'from_id':['from_id','source','from'],'to_id':['to_id','target','to']}.items():
            values=[tx[k] for k in aliases if k in tx]
            expected=evidence.get(field)
            # Missing values must not become the renderer's old default zero
            # amount or absent date. An incomplete evidence row is no basis for
            # a complete report item either; use another cited complete row.
            valid_type=lambda value: type(value) is int and value>=0 if field in {'amount','ts'} else isinstance(value,str) and bool(value)
            if not values or not valid_type(expected) or any(not valid_type(value) or value!=expected for value in values):errors.append(f'{key}:{field}')
    return errors
