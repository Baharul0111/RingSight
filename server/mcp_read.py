"""The frozen read catalogue. Only this server is mounted at public /mcp.

Every graph statement is a human-authored constant or an enum/integer template
in server/cypher. Model text is passed exclusively as query parameters.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import logging
import re
import time
import uuid
from functools import wraps
from pathlib import Path
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import ValidationError
from rapidfuzz import fuzz

from server.context import get_context,internal_control
from server.db import db
from server.guard import guard_read
from server.schemas import *

log = logging.getLogger(__name__)
read_srv = FastMCP("rs-read")
R = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}
_DIRECTORY = Path(__file__).parent / "cypher"
_QUERIES = {p.stem: p.read_text() for p in _DIRECTORY.glob("rs_*.cypher")}
_NAME_CACHE: dict[str, tuple[float, set[str]]] = {}


def query(name: str, **templates: Any) -> str:
    result = _QUERIES[name]
    for key, value in templates.items():
        result = result.replace("{" + key + "}", str(value))
    return result


async def read(q: str, params: dict | None = None, timeout: int = 5000) -> list[dict]:
    return await db.read(get_context().identity.tenant, q, params or {}, timeout=timeout)


def _offset(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        value = int(base64.urlsafe_b64decode(cursor.encode()).decode())
        if 0 <= value <= 100000:
            return value
    except (ValueError, UnicodeError, Exception) as exc:
        raise ValueError("invalid cursor") from exc
    raise ValueError("invalid cursor")


def _label(entity_id: str) -> str | None:
    return {"ACC": "Account", "PER": "Person", "DEV": "Device", "MER": "Merchant", "MRC": "Merchant", "PH": "Phone", "PHN": "Phone", "ADR": "Address", "ADDR": "Address", "ADD": "Address", "AL": "Alert", "ALT": "Alert", "ALERT": "Alert", "RES": "Restriction", "TX": "Transfer"}.get(entity_id.split("-", 1)[0].upper())


async def _resolve_exact(entity_id: str, allowed: tuple[str, ...] = ("Account", "Person", "Device", "Merchant", "Phone", "Address", "Alert", "Restriction")) -> dict | None:
    label = _label(entity_id)
    if label and label not in allowed:
        return None
    labels = [label] if label in allowed else list(allowed)
    for item in labels:
        rows = await read(query("rs_resolve_entity", label=item), {"q": entity_id})
        if rows:
            return rows[0]
    return None


async def _anchors(ids: list[str], allowed: tuple[str, ...] = ("Account",)) -> dict | None:
    for eid in ids:
        if not await _resolve_exact(eid, allowed):
            return {"outcome": "unknown_entity", "reason": "unknown_entity", "entity_id": eid, "suggestions": (await _resolve(ResolveInput(query=eid, kind="account")))["rows"][:5], "rows": []}
    return None


async def _coverage(as_of: int) -> dict:
    rails = await read("MATCH (r:Rail) RETURN r.name AS name,r.first_loaded AS first,r.last_loaded AS last")
    missing = [r for r in ("UPI", "NEFT", "RTGS", "IMPS", "CARD", "WALLET", "CASH", "XB") if r not in {x["name"] for x in rails}]
    return {"rails": rails, "missing_rails": missing, "banner": "Not in the graph ≠ nothing wrong"}


async def _dense(account_id: str) -> dict | None:
    rows = await read("MATCH (a:Account {id:$id}) RETURN coalesce(a.in_deg,0)+coalesce(a.out_deg,0) AS degree", {"id": account_id})
    if rows and rows[0]["degree"] > 500:
        return {"outcome": "tool_error", "reason": "hub_too_dense", "hint": "Narrow window_days or use rs_fan_pattern / rs_hub_rank", "rows": []}
    return None


async def _snapshot_available(as_of: int) -> tuple[bool, int | None]:
    # Rail coverage is fixed by ingestion. Ad-hoc future-edge test insertions
    # cannot change the declared coverage of a precomputed snapshot.
    rows = await read("MATCH (r:Rail) RETURN max(r.last_loaded) AS through")
    through = rows[0].get("through") if rows else None
    return through is None or as_of >= through, through


def _result(rows: list[dict], reason: str = "no_path_within_depth", **extra) -> dict:
    return {"outcome": "answered_with_path" if rows else "not_in_graph", "rows": rows, **({"reason": reason} if not rows else {}), **extra}


async def _resolve(args: ResolveInput) -> dict:
    labels = {"account": ["Account"], "person": ["Person"], "merchant": ["Merchant"], "device": ["Device"], "any": ["Account", "Person", "Merchant", "Device", "Phone", "Address", "Alert", "Restriction"]}[args.kind]
    q = args.query.strip()
    label = _label(q)
    as_of = args.as_of if args.as_of is not None else get_context().as_of
    if label == 'Transfer':
        # Transfer ids identify edges, not nodes. Never fall back to an
        # unfiltered prefix scan: a future transfer must remain undisclosed.
        exact = await read(query('rs_resolve_transfer'), {'q': q, 'as_of': as_of}) if args.kind == 'any' else []
        return {'outcome': 'resolved', 'rows': exact[:args.k]} if exact else {'outcome': 'unknown_entity', 'reason': 'unknown_entity', 'rows': [], 'suggestions': []}
    if label:
        if label not in labels:
            return {'outcome': 'unknown_entity', 'reason': 'unknown_entity', 'rows': [], 'suggestions': []}
        labels = [label]
    exact = []
    for label in labels:
        exact += await read(query('rs_resolve_alert') if label == 'Alert' else query("rs_resolve_entity", label=label), {"q": q, "as_of": as_of})
    if exact:
        return {"outcome": "resolved", "rows": exact[:args.k]}
    candidates = []
    for label in labels:
        candidates += await read(f"MATCH (e:{label}) WHERE e.id STARTS WITH $q" + (" AND e.raised_at <= $as_of" if label == 'Alert' else "") + f" RETURN '{label}' AS label,e.id AS id,0.9 AS score,'prefix' AS how LIMIT $k", {"q": q, "k": args.k, "as_of": as_of})
    if not candidates and not re.fullmatch(r"[A-Z]+-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", q):
        ft = "|".join(re.findall(r"[\w]+", q.lower(), flags=re.UNICODE))[:100]
        for label, prop in (("Person", "name_norm"), ("Merchant", "name")):
            if label not in labels or not ft:
                continue
            try:
                found = await read(f"CALL db.idx.fulltext.queryNodes('{label}',$q_ft) YIELD node,score RETURN '{label}' AS label,node.id AS id,node.{prop} AS _name_norm,score,'phonetic' AS how ORDER BY score DESC LIMIT 50", {"q_ft": ft})
            except Exception:
                found = []
            # Bounded server-side fallback also supports variant spellings when
            # the phonetic tokenizer returns no match. Names are then dropped.
            if not found:
                found = await read(f"MATCH (e:{label}) RETURN '{label}' AS label,e.id AS id,e.{prop} AS _name_norm LIMIT 1000")
            for row in found:
                score = fuzz.token_set_ratio(q.lower(), (row.pop("_name_norm", "") or "").lower()) / 100
                if score >= .52:
                    candidates.append({"id": row["id"], "label": label, "score": round(score, 3), "how": "fuzzy"})
    candidates.sort(key=lambda x: (-x["score"], x["id"]))
    if candidates:
        unique = list({r["id"]: r for r in candidates}.values())[:args.k]
        return {"outcome": "resolved" if len(unique) == 1 else "ambiguous", "rows": unique, "candidates": unique}
    # Suggestions contain opaque ids only; an unknown id is never silently used.
    nearest = []
    for label in labels[:1]:
        pool = await read(f"MATCH (e:{label})" + (" WHERE e.raised_at <= $as_of" if label == 'Alert' else "") + f" RETURN '{label}' AS label,e.id AS id LIMIT 1000", {"as_of": as_of})
        pool.sort(key=lambda x: -fuzz.ratio(q, x["id"]))
        nearest = [{**r, "score": round(fuzz.ratio(q, r["id"]) / 100, 3), "how": "fuzzy"} for r in pool[:min(args.k, 5)]]
    return {"outcome": "unknown_entity", "reason": "unknown_entity", "rows": [], "suggestions": nearest}


async def _recall(args: RecallInput) -> dict:
    unknown = await _anchors(args.entity_ids, ("Account", "Person", "Device"))
    if unknown:
        return unknown
    rows = []
    for label in ("Account", "Person", "Device"):
        group = [eid for eid in args.entity_ids if (_label(eid) == label)]
        if not group:
            continue
        found = await read(query("rs_recall_findings", label=label), {"ids": group, "as_of": args.as_of, "inc": args.include_unreviewed, "limit": 200})
        # Read the property map rather than nullable scalar columns. Rust6's
        # compact reply can panic when a missing optional field is a column.
        for row in found:
            finding=row.pop('finding')
            row.update({key:finding.get(key) for key in ('id','text','typology','confidence','author','reviewed','valid_from','valid_to','evidence_tool_call_ids','evidence_tx_ids')})
        rows += found
    merged = {}
    for row in rows:
        if row["id"] in merged:
            merged[row["id"]]["about"] = list(set(merged[row["id"]]["about"] + row.get("about", [])))
        else:
            merged[row["id"]] = row
    rows = sorted(merged.values(), key=lambda r: r["date_learned"], reverse=True)
    if args.query:
        rows = [r for r in rows if fuzz.partial_ratio(args.query.lower(), r["text"].lower()) >= 60]
    # Reviewed rows remain available; the agent sees no more than five agent
    # findings. Each recalled text is guarded again, including paraphrases.
    unreviewed = 0
    bounded = []
    for row in rows:
        if not row.get("reviewed"):
            unreviewed += 1
            if unreviewed > 5:
                continue
        row["memory_label"] = f"learned {row['date_learned']}, author {row.get('author')}, reviewed: {'yes' if row.get('reviewed') else 'no'}"
        bounded.append(row)
    # Some6.0.2 OPTIONAL MATCH plans dropped an otherwise valid Finding when
    # no pending action/decision existed. Enrich mandatory finding rows with
    # separate fixed queries; missing optional context is an empty list.
    finding_ids=[row['id'] for row in bounded]
    supersessions=await read(query('rs_recall_supersedes'),{'ids':finding_ids}) if finding_ids else []
    actions=await read(query('rs_recall_actions'),{'ids':finding_ids}) if finding_ids else []
    decisions=await read(query('rs_recall_decisions'),{'ids':finding_ids}) if finding_ids else []
    for row in bounded:
        row['supersedes']=next((item['supersedes'] for item in supersessions if item['finding_id']==row['id']),None)
        row['actions']=[{key:item[key] for key in ('pending','kind','status')} | {'decision':next((decision['decision'] for decision in decisions if decision['finding_id']==row['id'] and decision['pending']==item['pending']),None)} for item in actions if item['finding_id']==row['id']]
    call_ids=list(dict.fromkeys(cid for row in bounded for cid in (row.get('evidence_tool_call_ids') or [])))[:100]
    old_calls=await read('MATCH (t:ToolCall) WHERE t.id IN $ids RETURN t.id AS id,t.rows_json AS rows_json',{'ids':call_ids}) if call_ids else []
    old_rows={}
    for call in old_calls:
        try:old_rows[call['id']]=json.loads(call.get('rows_json') or '[]')
        except (ValueError,TypeError):old_rows[call['id']]=[]
    for row in bounded:
        row['evidence']=[{'tool_call_id':cid,'rows':old_rows[cid]} for cid in (row.get('evidence_tool_call_ids') or []) if cid in old_rows]
    return {"outcome": "answered_from_memory" if bounded else "not_in_memory", "rows": bounded}


async def _profile(args: ProfileInput) -> dict:
    unknown = await _anchors([args.account_id])
    if unknown:
        return unknown
    first = await read("MATCH (r:Rail) RETURN min(r.first_loaded) AS first")
    start = args.as_of - args.window_days * 86400
    if first and first[0].get("first") and start < first[0]["first"]:
        return _result([], "window_not_loaded", first_loaded=first[0]["first"])
    rows = await read(query("rs_account_profile"), {"id": args.account_id, "from": start, "as_of": args.as_of})
    if rows:
        peers = await read("MATCH (p:Account {type:$type}) RETURN percentileDisc(p.in_deg,0.5) AS in_deg_p50,percentileDisc(p.in_deg,0.95) AS in_deg_p95,percentileDisc(p.out_deg,0.5) AS out_deg_p50,percentileDisc(p.out_deg,0.95) AS out_deg_p95,count(p) AS n", {"type": rows[0]["type"]})
        rows[0]["peer_baseline"] = peers[0] if peers else {}
        rows[0]["edges"] = await read("MATCH (a:Account {id:$id})-[t:TX]-(b:Account) WHERE t.ts>$from AND t.ts<=$as_of RETURN t.id AS id,startNode(t).id AS source,endNode(t).id AS target,t.amount AS amount,t.ts AS ts,t.rail AS rail,t.memo AS memo,'TX' AS type ORDER BY t.ts DESC LIMIT $limit", {"id": args.account_id, "from": start, "as_of": args.as_of, "limit": args.limit})
        rows[0]["path_ids"] = [args.account_id]
        snapshot, through = await _snapshot_available(args.as_of)
        if not snapshot:
            for key in ("in_deg", "out_deg", "pagerank", "betweenness", "wcc_id", "lpa_id", "ring_id", "peer_baseline"):
                rows[0].pop(key, None)
            rows[0]["snapshot_warning"] = "Global algorithm properties and peer degree baselines are omitted before the snapshot coverage end. Dated transfer counts remain valid."
            rows[0]["algorithm_snapshot_through"] = through
    return _result(rows)


async def _neighbourhood(args: NeighbourhoodInput) -> dict:
    unknown = await _anchors([args.account_id])
    if unknown:
        return unknown
    if args.hops >= 3:
        dense = await _dense(args.account_id)
        if dense:
            return dense
    params = {"id": args.account_id, "from": args.as_of - args.window_days * 86400, "as_of": args.as_of, "min": args.min_amount, "limit": 201}
    rows={};neighbours=set()
    for length in range(1,args.hops+1):
        expansions=[]
        for i in range(1,length+1):
            source,target=f'n{i-1}',f'n{i}'
            relation={'out':f'-[r{i}:TX]->','in':f'<-[r{i}:TX]-','both':f'-[r{i}:TX]-'}[args.direction]
            edge=f"{{id:r{i}.id,amount:r{i}.amount,ts:r{i}.ts,rail:r{i}.rail,memo:r{i}.memo,source:startNode(r{i}).id,target:endNode(r{i}).id,type:'TX'}}"
            # CASE keeps this a filter over the anchored adjacency. The C
            # relationship-range-index plan otherwise drops inbound matches.
            expansions.append(f'MATCH ({source}){relation}({target}:Account) WHERE CASE WHEN r{i}.ts>$from AND r{i}.ts<=$as_of AND r{i}.amount>=$min THEN true ELSE false END\nWITH {target},path{i-1},edges{i-1},r{i} ORDER BY r{i}.ts,path{i-1}\nWITH {target},head(collect({{path_ids:path{i-1}+[n{i}.id],edges:edges{i-1}+[ {edge} ]}})) AS route{i}\nWITH {target},route{i}.path_ids AS path{i},route{i}.edges AS edges{i}')
        statement=query('rs_neighbourhood',expansions='\n'.join(expansions),hops=length)
        found=await read(statement,params,timeout=10000)
        for row in found:
            for source,target,edge in zip(row['path_ids'],row['path_ids'][1:],row['edges']):
                endpoints=(edge.get('source'),edge.get('target'))
                valid=endpoints==(source,target) if args.direction=='out' else endpoints==(target,source) if args.direction=='in' else endpoints in {(source,target),(target,source)}
                if not valid:return {'outcome':'tool_error','reason':'inconsistent_path','hint':'The graph returned inconsistent neighbourhood endpoints.','rows':[]}
        counted=await read(statement.split('RETURN b.id')[0]+' RETURN collect(DISTINCT b.id) AS ids',params,timeout=10000)
        for row in found:rows.setdefault(row['neighbour'],row)
        for row in counted:neighbours.update(row.get('ids') or [])
    return _result(sorted(rows.values(),key=lambda r:(r['hops'],r['neighbour'])),"entity_isolated",depth=args.hops,rows_total=len(neighbours))


async def _fan(args: FanInput) -> dict:
    unknown = await _anchors([args.account_id])
    if unknown:
        return unknown
    incoming = args.direction == "in"
    q = query("rs_fan_pattern", main="(s:Account)-[t:TX]->(a:Account {id:$id})" if incoming else "(a:Account {id:$id})-[t:TX]->(s:Account)", drain="(a)-[o:TX]->(d:Account)" if incoming else "(d:Account)-[o:TX]->(a)", leg_src="s.id" if incoming else "a.id", leg_dst="a.id" if incoming else "s.id", drain_src="a.id" if incoming else "d.id", drain_dst="d.id" if incoming else "a.id")
    rows = await read(q, {"id": args.account_id, "as_of": args.as_of, "win": args.window_hours * 3600, "drain": args.drain_hours * 3600, "min_cp": args.min_counterparties, "limit": args.limit})
    return _result(rows, "no_pattern_in_window", typology_hit=bool(rows), typology="fan_in" if incoming else "fan_out")


async def _cycles(args: CyclesInput) -> dict:
    unknown = await _anchors([args.account_id])
    if unknown:
        return unknown
    dense = await _dense(args.account_id)
    if dense:
        return dense
    branches = []
    for length in range(args.min_len, args.max_len + 1):
        nodes = ["a"] + list("bcde")[:length - 1] + ["a"]
        pattern = "(a:Account {id:$id})" + "".join(f"-[r{i+1}:TX]->({nodes[i+1]}{':Account' if i<length-1 else ''})" for i in range(length))
        predicates = [f"r{i}.ts>$from AND r{i}.ts<=$as_of" for i in range(1, length + 1)]
        # The C planner can bind disconnected legs in a longer cyclic match.
        # Check actual relationship endpoints, independently of node aliases.
        predicates += ['startNode(r1).id=$id',f'endNode(r{length}).id=$id']
        predicates += [f'endNode(r{i}).id=startNode(r{i+1}).id' for i in range(1,length)]
        predicates += [f"{nodes[i]}<>{nodes[j]}" for i in range(length) for j in range(i + 1, length)]
        if args.chronological:
            predicates += [f"r{i}.ts<r{i+1}.ts" for i in range(1, length)]
        predicates += [f"r{i+1}.amount >= r{i}.amount*(100-$decay)/100 AND r{i+1}.amount<=r{i}.amount" for i in range(1, length)]
        # Return the bound aliases themselves. On the pinned C engine, the
        # former path-object projection could pair one relationship with a
        # different path's next node across multiple UNION branches.
        edges = [f"{{id:r{i}.id,amount:r{i}.amount,ts:r{i}.ts,rail:r{i}.rail,memo:r{i}.memo,source:startNode(r{i}).id,target:endNode(r{i}).id,type:'TX'}}" for i in range(1, length + 1)]
        branches.append(query("rs_cycles", pattern=pattern, predicates=" AND ".join(predicates), length=length, accounts=','.join(node + '.id' for node in nodes), edges=','.join(edges)))
    rows = await read("\nUNION ALL\n".join(branches), {"id": args.account_id, "from": args.as_of - args.window_days * 86400, "as_of": args.as_of, "decay": args.max_decay_pct, "limit": 201}, timeout=10000)
    if not _consistent_cycles(rows):
        return {'outcome':'tool_error','reason':'inconsistent_path','hint':'The graph returned inconsistent cycle endpoints. Retry a narrower cycle window.','rows':[]}
    return _result(rows, "no_cycle_in_window", typology_hit=bool(rows), typology="cycle")


def _consistent_cycles(rows: list[dict]) -> bool:
    """Hop lists and repeated transfer ids must describe the same graph facts."""
    transfers = {}
    for row in rows:
        accounts, edges = row.get('accounts') or [], row.get('edges') or []
        length = row.get('len')
        if length not in {3,4,5} or len(edges)!=length or len(accounts)!=length+1:
            return False
        if accounts[0]!=accounts[-1] or len(set(accounts[:-1]))!=length:
            return False
        for source,target,edge in zip(accounts,accounts[1:],edges):
            if not isinstance(edge,dict) or edge.get('source')!=source or edge.get('target')!=target:
                return False
            identifier=edge.get('id')
            facts=tuple(edge.get(field) for field in ('source','target','amount','ts','rail'))
            if not identifier or (identifier in transfers and transfers[identifier]!=facts):
                return False
            transfers[identifier]=facts
    return True


async def _scatter(args: ScatterInput) -> dict:
    unknown = await _anchors([args.account_id])
    if unknown:
        return unknown
    dense = await _dense(args.account_id)
    if dense:
        return dense
    rows = await read(query("rs_scatter_gather" if args.mode == "scatter_gather" else "rs_gather_scatter"), {"id": args.account_id, "as_of": args.as_of, "win": args.window_hours * 3600, "min": args.min_mules, "limit": 201}, timeout=10000)
    return _result(rows, "no_pattern_in_window", typology_hit=bool(rows), typology=args.mode)


async def _paths(args: PathInput) -> dict:
    unknown = await _anchors([args.src_id, args.dst_id])
    if unknown:
        return unknown
    dense = await _dense(args.src_id)
    if dense:
        return dense
    params = {"src": args.src_id, "dst": args.dst_id, "as_of": args.as_of, "from": 0, "limit": args.k, "rel_types": args.rel_types, "wprop": "w" if args.weight == "hops" else "amount", "max_hops": args.max_hops, "k": args.k}
    # The graph algorithm is visible in the trace. Its timeless candidate rows
    # never leave the server; the bounded Cypher below supplies the temporal
    # evidence, so a newly inserted future shortcut cannot leak into an answer.
    await read(query("rs_path_algorithm"), params, timeout=10000)
    rows = await read(query("rs_path_between", rels="|".join(args.rel_types), hops=args.max_hops, weight="w" if args.weight == "hops" else "amount"), params, timeout=10000)
    return _result(rows, "no_path_within_depth", depth=args.max_hops, point_in_time=True, algorithm="algo.SPpaths + bounded point-in-time Cypher")


async def _ring(args: RingInput) -> dict:
    unknown = await _anchors([args.account_id])
    if unknown:
        return unknown
    available, through = await _snapshot_available(args.as_of)
    if not available:
        return {"outcome": "tool_error", "reason": "historical_snapshot_unavailable", "hint": "The precomputed community includes data after this as_of. Use dated neighbourhood or path tools instead.", "rows": [], "snapshot_through": through}
    prop = {"shared_ids": "ring_id", "money_wcc": "wcc_id", "money_lpa": "lpa_id"}[args.basis]
    size = await read(query("rs_ring_members", prop=prop), {"id": args.account_id, "min": args.min_size, "max": args.max_size})
    if not size or not size[0]["in_bounds"]:
        return _result([], "singleton_or_out_of_bounds", size=size[0].get("n", 0) if size else 0)
    params = {"cid": size[0]["cid"], "n": size[0]["n"], "as_of": args.as_of, "limit": args.limit}
    rows = await read(query("rs_ring_details", prop=prop), params)
    edges = await read(f"MATCH (m:Account {{{prop}:$cid}})-[t:TX]->(n:Account {{{prop}:$cid}}) WHERE t.ts<=$as_of RETURN t.id AS id,m.id AS source,n.id AS target,t.amount AS amount,t.ts AS ts,t.rail AS rail,t.memo AS memo,'TX' AS type ORDER BY t.ts LIMIT $limit", params)
    shares = await read(f"MATCH (m:Account {{{prop}:$cid}})-[s:SHARES_STRONG]-(o:Account {{{prop}:$cid}}) WHERE m.id<o.id AND s.computed_at<=$as_of RETURN m.id AS source,o.id AS target,s.weight AS weight,s.kinds AS kinds,'SHARES_STRONG' AS type LIMIT $limit", params)
    for row in rows:
        row["edges"] = edges + shares
        row["computed_at"] = size[0]["computed_at"]
        row["members"] = sorted(row.get("members", []),key=lambda member:member['id'])[:args.limit]
    return _result(rows, computed_at=size[0]["computed_at"], algorithm="algo.WCC" if args.basis != "money_lpa" else "algo.labelPropagation", typology_hit=bool(rows), typology="shared_identifier" if args.basis == "shared_ids" else args.basis)


async def _hubs(args: HubInput) -> dict:
    available, through = await _snapshot_available(args.as_of)
    if not available:
        return {"outcome": "tool_error", "reason": "historical_snapshot_unavailable", "hint": "These precomputed ranks include data after this as_of. Use dated account profiles instead.", "rows": [], "snapshot_through": through}
    scope = "" if args.scope == "global" else " {" + ("ring_id" if args.scope == "ring" else "wcc_id") + ":$sid}"
    rows = await read(query("rs_hub_rank", scope=scope, metric=args.metric), {"sid": args.scope_id, "inc": args.include_legit_hubs, "limit": args.top_k, "exact": args.metric != "betweenness"})
    meta = await read("MATCH (m:Meta) RETURN m.betweenness_samples AS samples LIMIT 1") if args.metric == "betweenness" else []
    samples = meta[0].get("samples") if meta else None
    return _result(rows, "scope_not_in_graph", exact=args.metric != "betweenness", sampling_size=samples, algorithm={"pagerank": "algo.pageRank", "betweenness": "algo.betweenness (sampled" + (f" {samples}" if samples else "") + ")", "in_deg": "degree", "out_deg": "degree"}[args.metric], computed_at=rows[0].get("computed_at") if rows else None)


async def _flow(args: FlowInput) -> dict:
    unknown = await _anchors(args.source_ids + args.sink_ids)
    if unknown:
        return unknown
    projection = await read("MATCH (a:Account)-[f:FLOW]->(b:Account) RETURN max(f.ts) AS through,max(f.computed_at) AS computed_at,count(f) AS n")
    if not projection or not projection[0].get("n"):
        return {"outcome": "tool_error", "reason": "projection_not_available", "hint": "The seed-time aggregated flow projection is unavailable. Run the seed precompute before using max-flow.", "rows": [], "point_in_time": False}
    if projection[0]["through"] > args.as_of:
        return {"outcome": "tool_error", "reason": "historical_projection_unavailable", "hint": "Historical max-flow needs a windowed projection. Use rs_path_between for point-in-time paths.", "rows": [], "point_in_time": False}
    try:
        rows = await read(query("rs_money_flow"), {"sources": args.source_ids, "sinks": args.sink_ids, "cap": "amount" if args.capacity == "amount" else "w"}, timeout=20000)
    except Exception as exc:
        if "multi-edges" in str(exc):
            return {"outcome": "tool_error", "reason": "parallel_edges_require_projection", "hint": "This engine requires an aggregated money-flow projection for repeated transfers. Use rs_path_between for exact dated transfers.", "rows": [], "point_in_time": False, "algorithm": "algo.maxFlow"}
        raise
    for row in rows:
        row["projection_note"] = "Aggregated seed-time FLOW, not current raw transfers. Repeated TX amounts are summed; count capacity uses transfer count."
        evidence = []
        for edge in row.get("flow_edges", [])[:args.limit]:
            evidence += await read("MATCH (a:Account {id:$src})-[t:TX]->(b:Account {id:$dst}) WHERE t.ts<=$through AND t.ts<=$as_of RETURN t.id AS id,a.id AS source,b.id AS target,t.amount AS amount,t.ts AS ts,t.rail AS rail,'TX' AS type ORDER BY t.ts LIMIT $limit", {"src": edge["source"], "dst": edge["target"], "through": edge["ts"], "as_of": args.as_of, "limit": args.limit})
        row["edges"] = evidence[:args.limit]
    return _result([r for r in rows if r.get("maxFlow", 0) > 0], "no_flow", point_in_time=False, computed_at=projection[0]["computed_at"], projection_through=projection[0]["through"], algorithm="algo.maxFlow (aggregated FLOW projection)")


async def _direct_shared(account_id: str, args: SharedInput) -> list[dict]:
    params = {"id": account_id, "as_of": args.as_of, "max_deg": args.max_identifier_degree, "limit": 201}
    parts = []
    if "device" in args.kinds:
        parts.append(query("rs_shared_identifiers"))
    for kind, label, rel in (("phone", "Phone", "HAS_PHONE"), ("address", "Address", "HAS_ADDRESS")):
        if kind in args.kinds:
            parts.append(f"MATCH (a:Account {{id:$id}})<-[o1:OWNS]-(p:Person)-[:{rel}]->(x:{label})<-[:{rel}]-(q:Person)-[o2:OWNS]->(b:Account) WHERE b<>a AND p<>q AND x.degree<=$max_deg AND coalesce(o1.since,0)<=$as_of AND coalesce(o2.since,0)<=$as_of RETURN b.id AS linked,'Account' AS kind,'hard' AS strength,1 AS hops,[a.id,p.id,x.id,q.id,b.id] AS path_ids,['OWNS','{rel}','{rel}','OWNS'] AS link_kinds,x.degree AS identifier_degree LIMIT $limit")
    if "owner" in args.kinds:
        parts.append("MATCH (a:Account {id:$id})<-[o1:OWNS]-(p:Person)-[o2:OWNS]->(b:Account) WHERE b<>a AND coalesce(o1.since,0)<=$as_of AND coalesce(o2.since,0)<=$as_of WITH a,p,b,count(b) AS n RETURN b.id AS linked,'Account' AS kind,'hard' AS strength,1 AS hops,[a.id,p.id,b.id] AS path_ids,['OWNS','OWNS'] AS link_kinds,1 AS identifier_degree LIMIT $limit")
    result = []
    for part in parts:
        result += await read(part, params)
    return result


async def _shared(args: SharedInput) -> dict:
    unknown = await _anchors([args.account_id])
    if unknown:
        return unknown
    direct = await _direct_shared(args.account_id, args)
    rows = list(direct)
    if args.hops >= 2:
        materialized = await read(query("rs_shared_materialized", hops=args.hops), {"id": args.account_id, "as_of": args.as_of, "kinds": args.kinds, "limit": 201}, timeout=10000)
        cache = {args.account_id: direct}
        for row in materialized:
            concrete = [args.account_id]
            kinds = []
            valid = True
            for source, target in zip(row["path_ids"], row["path_ids"][1:]):
                if source not in cache:
                    cache[source] = await _direct_shared(source, args)
                links = [r for r in cache[source] if r["linked"] == target]
                if not links:
                    valid = False
                    break
                chosen = min(links, key=lambda r: (len(r["path_ids"]),tuple(r["path_ids"])))
                concrete += chosen["path_ids"][1:]
                kinds += chosen["link_kinds"]
            if valid:
                rows.append({**row, "path_ids": concrete, "link_kinds": kinds})
    unique = {}
    for row in sorted(rows, key=lambda r: (r["hops"],len(r["path_ids"]),tuple(r["path_ids"]))):
        unique.setdefault(row["linked"], row)
    return _result(list(unique.values()), "no_shared_identifiers_at_depth", depth=args.hops, typology_hit=bool(unique), typology="shared_identifier", algorithm="weighted identifier projection")


async def _restrictions(args: RestrictionInput) -> dict:
    entity = await _resolve_exact(args.entity_id, ("Account", "Person"))
    if not entity:
        return {"outcome": "unknown_entity", "rows": [], "entity_id": args.entity_id, "suggestions": []}
    closure = "RETURN e.id AS id,restrictions" if entity["label"] == "Person" else "OPTIONAL MATCH (e)-[t:TX]->(b:Account) WHERE e.status='closure_pending' AND t.ts>e.closure_requested_at AND t.ts<=$as_of RETURN e.id AS id,e.status AS status,restrictions,count(t) AS tx_after_closure_request,coalesce(sum(t.amount),0) AS amount_after_closure_request"
    rows = await read(query("rs_check_restrictions", label=entity["label"], closure=closure), {"id": args.entity_id, "as_of": args.as_of})
    for row in rows:
        row["restrictions"] = [r for r in row["restrictions"] if r.get("id")]
        row["path_ids"] = [args.entity_id] + [r["id"] for r in row["restrictions"]]
    # A non-empty account row constitutes an affirmative restriction check,
    # even when restrictions=[]; this is distinct from an unknown account.
    return {"outcome": "answered_with_path" if any(r["restrictions"] for r in rows) else "not_in_graph", "reason": "no_restrictions" if not any(r["restrictions"] for r in rows) else None, "rows": rows, "typology_hit": False}


async def _coverage_tool(args: CoverageInput) -> dict:
    rows = await read(query("rs_coverage_status"), {"rail": args.rail.upper() if args.rail else None, "f": args.from_date, "t": args.to_date})
    if args.rail and (not rows or args.rail.upper() not in [r["name"] for r in rows[0]["rails"]]):
        return {"outcome": "not_in_graph", "reason": "rail_not_ingested", "rail": args.rail.upper(), "rows": rows}
    return _result(rows)


READ_TOOLS = {"rs_resolve_entity": _resolve, "rs_recall_findings": _recall, "rs_account_profile": _profile, "rs_neighbourhood": _neighbourhood, "rs_fan_pattern": _fan, "rs_cycles": _cycles, "rs_scatter_gather": _scatter, "rs_path_between": _paths, "rs_ring_members": _ring, "rs_hub_rank": _hubs, "rs_money_flow": _flow, "rs_shared_identifiers": _shared, "rs_check_restrictions": _restrictions, "rs_coverage_status": _coverage_tool}
TOOL_SCHEMAS = {name: model.model_json_schema() for name, model in INPUT_MODELS.items()}


async def _sanitize(value: Any, key: str = "", names: set[str] | None = None) -> tuple[Any, int]:
    if isinstance(value, dict):
        out, hits = {}, 0
        for k, v in value.items():
            if k.startswith("_") or k in {"name_norm", "owner_name", "address", "merchant_name", "decided_by"} or (k == "name" and v not in {"UPI", "NEFT", "RTGS", "IMPS", "CARD", "WALLET", "CASH", "XB"}):
                continue
            clean, n = await _sanitize(v, k, names)
            out[k] = clean
            hits += n
        return out, hits
    if isinstance(value, list):
        out, hits = [], 0
        for item in value:
            clean, n = await _sanitize(item, key, names)
            out.append(clean)
            hits += n
        return out, hits
    if isinstance(value, str) and (key in {"memo", "text", "rationale", "decision_reason"} or (key == "source" and not value.startswith(("ACC-", "PER-", "DEV-", "MER-")))):
        if key == "memo":
            value = re.sub(r"(?<!\w)(?:\+?\d[\d ()-]{8,}\d)(?!\w)", "<phone>", value)
            value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "<email>", value)
            if names:
                value = re.sub(r"\b[\w']+\b", lambda m: "<name>" if m.group(0).lower() in names else m.group(0), value)
        guarded, hits = guard_read(value, field=key, source="graph")
        return guarded, hits if isinstance(hits, int) else len(hits)
    if isinstance(value, float) and value.is_integer() and key in {"amount", "total", "in_sum", "out_sum", "drain_sum", "scattered", "gathered", "internal_amount", "amount_after_closure_request", "maxFlow"}:
        return int(value), 0
    if isinstance(value,str):
        # A free-text value in a new graph field must not bypass the scanner.
        from server.guard import scan
        if scan(value,'read'):
            guarded,hits=guard_read(value,field=key or 'text',source='graph')
            return guarded,hits
    return value, 0


def _paths_from_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    nodes, edges = {}, {}

    def node(eid):
        if isinstance(eid, str) and _label(eid) not in {None, 'Transfer'}:
            nodes[eid] = {"id": eid, "label": _label(eid)}

    def visit(value):
        if isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            for k, v in value.items():
                if k in {"path_ids", "node_ids", "accounts"} and isinstance(v, list):
                    for eid in v:
                        node(eid)
                    if k == "path_ids":
                        kinds = value.get("link_kinds", [])
                        for i, (a, b) in enumerate(zip(v, v[1:])):
                            kind = kinds[i] if i < len(kinds) and isinstance(kinds[i], str) else "LINK"
                            src, dst = a, b
                            if (kind == "OWNS" and a.startswith("ACC-")) or (kind == "USES_DEVICE" and a.startswith("DEV-")) or (kind in {"HAS_PHONE", "HAS_ADDRESS"} and b.startswith("PER-")):
                                src, dst = b, a
                            edges[f"{a}:{b}:{kind}"] = {"source": src, "target": dst, "type": kind}
                elif k in {"source", "target", "from", "to", "id", "linked", "account", "collector", "gatherer"}:
                    node(v)
                visit(v)
            src, dst = value.get("source", value.get("from")), value.get("target", value.get("to"))
            if isinstance(src, str) and isinstance(dst, str):
                eid = value.get("id") or value.get("tx") or f"{src}:{dst}:{value.get('type','LINK')}"
                edges[eid] = {**value, "id": eid, "source": src, "target": dst}
            if value.get("out_tx") and value.get("mule"):
                for prefix, src, dst in (("out", value.get("source"), value["mule"]), ("in", value["mule"], value.get("gatherer"))):
                    if src and dst:
                        eid = value[prefix + "_tx"]
                        edges[eid] = {"id": eid, "source": src, "target": dst, "type": "TX", "amount": value[prefix + "_amt"], "ts": value[prefix + "_ts"], "rail": value.get(prefix + "_rail")}
                        node(src)
                        node(dst)
    visit(rows)
    return list(nodes.values())[:1000], list(edges.values())[:2000]


async def run_tool(name: str, args: dict | None = None) -> dict:
    ctx = get_context()
    started = time.perf_counter()
    call_id = str(uuid.uuid4())
    arguments = args or {}
    as_of = arguments.get("as_of") or ctx.as_of
    try:
        if ctx.session_id and not internal_control.get():
            if ctx.tool_count >= 10:
                raise ValueError("investigation tool-call budget exhausted")
            ctx.tool_count += 1
        if name not in INPUT_MODELS:
            raise ValueError("unknown tool")
        parsed = INPUT_MODELS[name].model_validate(arguments)
        parsed.as_of = parsed.as_of if parsed.as_of is not None else ctx.as_of
        as_of = parsed.as_of
        offset = _offset(parsed.cursor)
        result = await READ_TOOLS[name](parsed)
        total = result.pop("rows_total", len(result.get("rows", [])))
        all_rows = result.get("rows", [])
        result["rows"] = all_rows[offset:offset + parsed.limit]
        result["rows_total"] = total
        result["truncated"] = total > offset + parsed.limit
        if result["truncated"]:
            result["next_cursor"] = base64.urlsafe_b64encode(str(offset + parsed.limit).encode()).decode()
        coverage = await _coverage(as_of) if name != "rs_coverage_status" else None
        if coverage:
            result["coverage_warning"] = coverage
        # Only memo-bearing results need the synthetic name dictionary. It is
        # server-side, scoped per tenant, and never enters an envelope.
        names = set()
        if '"memo"' in json.dumps(result, default=str):
            tenant = ctx.identity.tenant
            cached = _NAME_CACHE.get(tenant)
            if not cached or time.monotonic() - cached[0] > 600:
                # Return one collection row: the free-tier resultset row cap
                # must not truncate a tenant's server-only name dictionary.
                values = await read("MATCH (p:Person) RETURN collect(p.name_norm) AS values")
                names = {word.lower() for row in values for value in row.get("values", []) for word in str(value or "").split() if len(word) >= 3}
                _NAME_CACHE[tenant] = (time.monotonic(), names)
            else:
                names = cached[1]
        result, hits = await _sanitize(result, names=names)
        result["guard_hits"] = hits
        result["path_nodes"], result["path_edges"] = _paths_from_rows(result.get("rows", []))
    except ValidationError as exc:
        result = {"outcome": "tool_error", "reason": "validation", "hint": "; ".join(e["msg"] for e in exc.errors(include_input=False)), "rows": [], "rows_total": 0, "truncated": False, "guard_hits": 0, "path_nodes": [], "path_edges": []}
    except Exception as exc:
        reason = "budget_exhausted" if "tool-call budget" in str(exc) else "timeout" if "timeout" in str(exc).lower() or isinstance(exc, TimeoutError) else "validation" if isinstance(exc, ValueError) else "db_unavailable"
        result = {"outcome": "tool_error", "reason": reason, "hint": "Try narrower bounds." if reason == "timeout" else "Check the typed tool arguments." if reason == "validation" else "The graph is unavailable; retry shortly.", "rows": [], "rows_total": 0, "truncated": False, "guard_hits": 0, "path_nodes": [], "path_edges": []}
        log.warning("read_tool_failed tool=%s reason=%s exception_type=%s", name, reason, type(exc).__name__)
    safe_args = {k: ("<redacted>" if k == "query" else v) for k, v in arguments.items()}
    result.update(tool=name, name=name, args=safe_args, as_of=as_of, elapsed_ms=round((time.perf_counter() - started) * 1000, 2), tool_call_id=call_id, rows_returned=len(result.get("rows", [])))
    if result.get("reason"):
        result["is_error"] = result["outcome"] == "tool_error"
    if ctx.session_id:
        try:
            digest = hashlib.sha256(json.dumps(result["rows"], sort_keys=True, default=str).encode()).hexdigest()
            await db.write(ctx.identity.tenant, "MATCH (s:Session {id:$sid}) CREATE (t:ToolCall {id:$id,seq:$seq,tool:$tool,args_json:$args,rows_json:$rows,rows_total:$total,rows_returned:$returned,truncated:$truncated,elapsed_ms:$ms,rows_sha256:$hash,guard_hits:$hits,at:$at}) CREATE (t)-[:IN]->(s) RETURN t.id AS id", {"sid": ctx.session_id, "id": call_id, "seq": len(ctx.calls) + 1, "tool": name, "args": json.dumps(safe_args), "rows": json.dumps(result["rows"], default=str), "total": result["rows_total"], "returned": len(result["rows"]), "truncated": result["truncated"], "ms": result["elapsed_ms"], "hash": digest, "hits": result["guard_hits"], "at": int(time.time())})
        except Exception as exc:
            log.warning("tool_audit_unavailable exception_type=%s", type(exc).__name__)
    await ctx.trace(result)
    log.info("read_tool %s", json.dumps({k: v for k, v in result.items() if k in {"tool", "args", "elapsed_ms", "rows_total", "outcome", "guard_hits"}}, default=str))
    return result


call_tool = run_tool

_DESCRIPTIONS = {
    "rs_resolve_entity": "Resolve an account, person, merchant or device by exact id, prefix or guarded fuzzy name. Only opaque ids reach the model; ambiguous candidates are never silently chosen. input_example: {\"query\":\"ACC-4471\",\"kind\":\"account\"}.",
    "rs_recall_findings": "Recall bi-temporal findings before reasoning about resolved entities. Every row states when it was learned, author and human-review status, and at most five unreviewed findings return. input_example: {\"entity_ids\":[\"ACC-4471\"]}.",
    "rs_account_profile": "Profile dated inbound and outbound transfers against same-type peers. Owner and device ids, active restrictions, alerts and precomputed algorithm timestamps accompany evidence. input_example: {\"account_id\":\"ACC-4471\",\"window_days\":90}.",
    "rs_neighbourhood": "Walk one to four money-transfer hops within a dated window. Every returned hop has exact ids, paise amounts, timestamps and rails; no result means no connection within these bounds. input_example: {\"account_id\":\"ACC-4471\",\"hops\":4}.",
    "rs_fan_pattern": "Detect bounded fan-in or fan-out with the subsequent opposite-direction drain. Legitimate merchants and payroll can also produce this pattern, so consult the peer profile before proposing action. input_example: {\"account_id\":\"ACC-4471\",\"direction\":\"in\"}.",
    "rs_cycles": "Detect chronological cycles of three to five distinct accounts with bounded amount decay. Dense hubs are refused before traversal and all legs are at or before as_of. input_example: {\"account_id\":\"ACC-4471\",\"min_len\":3,\"max_len\":5}.",
    "rs_scatter_gather": "Detect a source scattering to several mules which then gather, or a collector gathering then scattering. Exact transfer legs and temporal ordering support every pattern; absence never establishes innocence. input_example: {\"account_id\":\"ACC-4471\",\"mode\":\"scatter_gather\"}.",
    "rs_path_between": "Find directed shortest paths with FalkorDB algo.SPpaths and a bounded temporal evidence query. Future algorithm candidates are never exposed; no path is qualified by max_hops. input_example: {\"src_id\":\"ACC-4471\",\"dst_id\":\"ACC-55820\",\"max_hops\":4}.",
    "rs_ring_members": "Read precomputed shared-identifier or money communities and their internal evidence. A count-before-collect guard refuses giant components and computed_at shows algorithm freshness. input_example: {\"account_id\":\"ACC-4471\",\"basis\":\"shared_ids\"}.",
    "rs_hub_rank": "Rank accounts by graph-native precomputed PageRank, sampled betweenness or degree. Merchants, payroll and exchanges are excluded by default, sample size comes from Meta and historical snapshots are refused. input_example: {\"scope\":\"global\",\"metric\":\"pagerank\"}.",
    "rs_money_flow": "Run FalkorDB max-flow on the dated, aggregated seed-time FLOW projection using amount or transfer-count capacity. Calls before the projection coverage end are refused, later raw transfers are excluded, and point_in_time:false clearly labels snapshot scope. input_example: {\"source_ids\":[\"ACC-4471\"],\"sink_ids\":[\"ACC-55820\"]}.",
    "rs_shared_identifiers": "Follow shared devices, phones, addresses and owners with identifier-degree guards. Materialized multi-hop links are expanded into actual identifier ids so every displayed hop is auditable. input_example: {\"account_id\":\"ACC-4471\",\"hops\":2}.",
    "rs_check_restrictions": "Check dated restrictions and activity after a closure request for a resolved entity. This never changes an account and every proposed action repeats this check server-side. input_example: {\"entity_id\":\"ACC-4471\"}.",
    "rs_coverage_status": "Read loaded rails, covered dates and mismatched ingestion-day counts directly from the tenant graph. CASH and cross-border rail absence produce an honest not-in-graph outcome. input_example: {\"rail\":\"CASH\"}.",
}


def _register(name: str):
    async def invoke(**kwargs):
        return await run_tool(name, kwargs)
    invoke.__name__ = name
    invoke.__doc__ = _DESCRIPTIONS[name]
    params = []
    annotations = {}
    for field_name, field in INPUT_MODELS[name].model_fields.items():
        annotation = Annotated[field.annotation, *field.metadata] if field.metadata else field.annotation
        annotations[field_name] = annotation
        params.append(inspect.Parameter(field_name, kind=inspect.Parameter.KEYWORD_ONLY, annotation=annotation, default=inspect.Parameter.empty if field.is_required() else field.default))
    invoke.__annotations__ = annotations
    invoke.__signature__ = inspect.Signature(params, return_annotation=dict)
    read_srv.tool(name=name, description=_DESCRIPTIONS[name], annotations=R)(invoke)


for _name in READ_TOOLS:
    _register(_name)

CATALOGUE_HASH = hashlib.sha256(json.dumps(TOOL_SCHEMAS, sort_keys=True).encode()).hexdigest()
