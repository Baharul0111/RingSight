"""No-model planted-pattern measurement on an explicitly local seeded graph.

Ground truth is read only by this offline harness. Runtime tools cannot import
this module and never read data/rings.json. Metrics are synthetic, demo-only.
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import time
from collections import defaultdict
from pathlib import Path

from server.context import Identity, Investigation, current_context
from server.db import db
from server.mcp_read import run_tool


async def evaluate(tenant: str, output: Path):
    url = os.environ.get("RS_TEST_REDIS_URL", "")
    if not ("localhost" in url or "127.0.0.1" in url):
        raise RuntimeError("These evaluations require RS_TEST_REDIS_URL pointing at local FalkorDB")
    manifest = json.loads(Path("data/manifest.json").read_text())
    rings = json.loads(Path("data/rings.json").read_text())
    as_of = manifest["as_of"]
    current_context.set(Investigation(Identity("offline_eval", "analyst", tenant), as_of=as_of))
    records, errors = [], []
    for ring in rings:
        pattern, account = ring["typology"], ring["seed_account"]
        args = {"account_id": account, "limit": 200}
        tool = ring["expected_tools"][0]
        if tool == "rs_fan_pattern":
            args.update(direction="in" if pattern == "fan_in" else "out", window_hours=720)
        elif tool == "rs_neighbourhood":
            args.update(hops=4, direction="both")
        elif tool == "rs_scatter_gather":
            args.update(mode=pattern, window_hours=720)
        result = await run_tool(tool, args)
        found = set(re.findall(r"ACC-[A-Za-z0-9]+", json.dumps(result["rows"]))) | ({account} if result["rows"] else set())
        expected = set(ring["accounts"])
        profile = await db.read(tenant, "MATCH (a:Account {id:$id}) RETURN a.in_deg AS in_deg,a.ring_id AS ring_id", {"id": account})
        record = {"ring_id": ring["ring_id"], "typology": pattern, "tool": tool, "seed": account, "expected_members": len(expected), "recalled_members": len(found & expected), "member_recall": len(found & expected) / len(expected), "returned_accounts": len(found), "member_precision": len(found & expected) / len(found) if found else 0, "recipient_in_degree": profile[0]["in_deg"], "elapsed_ms": result["elapsed_ms"], "outcome": result["outcome"]}
        if result["outcome"] == "tool_error":
            errors.append({"ring_id": ring["ring_id"], "reason": result["reason"]})
        records.append(record)
    degrees = sorted(r["recipient_in_degree"] for r in records)
    thresholds = [degrees[len(degrees)//3], degrees[len(degrees)*2//3]]
    groups = defaultdict(list)
    terciles = defaultdict(list)
    for row in records:
        groups[row["typology"]].append(row["member_recall"])
        tercile = "low" if row["recipient_in_degree"] <= thresholds[0] else "middle" if row["recipient_in_degree"] <= thresholds[1] else "high"
        row["recipient_in_degree_tercile"] = tercile
        terciles[tercile].append(row["member_recall"])
    ranking = await run_tool("rs_hub_rank", {"scope": "global", "metric": "pagerank", "top_k": 10})
    hub_truth = {r["hub_account"] for r in rings}
    predicted = [r["id"] for r in ranking["rows"]]
    legit = set(manifest["legitimate_hubs"])
    hub_metrics = {}
    for metric in ("pagerank", "in_deg", "out_deg", "betweenness"):
        ranked = ranking if metric == "pagerank" else await run_tool("rs_hub_rank", {"scope": "global", "metric": metric, "top_k": 10})
        ranked_ids = [row["id"] for row in ranked["rows"]]
        hub_metrics[metric] = {"precision_at_10": len(set(ranked_ids) & hub_truth) / len(ranked_ids) if ranked_ids else 0, "legitimate_hubs_returned": len(set(ranked_ids) & legit), "ids": ranked_ids}
    controls = []
    for i in range(20):
        result = await run_tool("rs_account_profile", {"account_id": f"ACC-NONEXISTENT{i}"})
        controls.append(result["outcome"] == "unknown_entity")
    for _ in range(5):
        result = await run_tool("rs_coverage_status", {"rail": "CASH"})
        controls.append(result["outcome"] == "not_in_graph" and result["reason"] == "rail_not_ingested")
    body = {"suite": "structural-read-patterns", "synthetic_demo_only": True, "model_calls": 0, "local_graph": "rs_"+tenant.removeprefix("rs_"), "as_of": as_of, "executed_at": int(time.time()), "passed": not errors and all(controls) and not (set(predicted) & legit), "errors": errors,
            "per_typology": {k:{"n":len(v),"mean_member_recall":statistics.mean(v)} for k,v in groups.items()},
            "recipient_in_degree_terciles": {k:{"n":len(v),"mean_member_recall":statistics.mean(v)} for k,v in terciles.items()},
            "hub_precision_at_10": len(set(predicted)&hub_truth)/len(predicted) if predicted else 0, "hub_metric": "pagerank", "legitimate_hubs_present":len(legit), "legitimate_hubs_returned":len(set(predicted)&legit), "hub_ids":predicted,
            "hub_metrics": hub_metrics,
            "unknown_entities": {"cases":20,"passed":sum(controls[:20])}, "cash_abstentions":{"cases":5,"passed":sum(controls[20:])}, "rings":records,
            "method": "Exact frozen matching-pattern tool on every planted seed; account ids extracted only from returned evidence rows, including the anchor when rows exist. Report measured recall, not a real-world detection claim. Hub precision compares global top-10 PageRank retail/business accounts with planted hub_account ground truth; legitimate types are excluded by the tool."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(body, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"passed":body["passed"],"patterns":body["per_typology"],"hub_precision_at_10":body["hub_precision_at_10"],"errors":errors}))
    return body


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--tenant",default="bank_a")
    parser.add_argument("--output",type=Path,default=Path("evals/results/structural-patterns.json"))
    options=parser.parse_args()
    result=asyncio.run(evaluate(options.tenant,options.output))
    raise SystemExit(0 if result["passed"] else 1)
