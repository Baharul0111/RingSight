"""Export and restore reviewed/labelled findings without loading answer keys."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from server.db import GraphDB

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "findings_snapshot.json"


def export_snapshot(database: GraphDB, graph: str = "rs_bank_a", path: Path = DEFAULT_PATH) -> int:
    records = database.sync_read(graph, "MATCH (f:Finding) OPTIONAL MATCH (f)-[:ABOUT]->(e) RETURN properties(f) AS finding,collect({id:e.id,labels:labels(e)}) AS entities LIMIT 2000")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema": 1, "synthetic": True, "findings": records}, indent=2, sort_keys=True) + "\n")
    return len(records)


def restore_snapshot(database: GraphDB, graph: str = "rs_bank_a", path: Path = DEFAULT_PATH) -> int:
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    records = data.get("findings", [])[:2000]
    count = 0
    for record in records:
        finding = record.get("finding", {})
        if not finding.get("id") or not finding.get("idem_key"):
            continue
        database.sync_write(graph, "MERGE (f:Finding {idem_key:$key}) ON CREATE SET f = $props RETURN f.id AS id",
                            {"key": finding["idem_key"], "props": finding})
        for entity in record.get("entities", []):
            label = next((l for l in entity.get("labels", []) if l in ("Account", "Person", "Device")), None)
            if label and entity.get("id"):
                database.sync_write(graph, f"MATCH (f:Finding {{id:$fid}}),(e:{label} {{id:$eid}}) MERGE (f)-[:ABOUT]->(e)",
                                    {"fid": finding["id"], "eid": entity["id"]})
        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "restore"))
    parser.add_argument("--graph", default="rs_bank_a")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    operation = export_snapshot if args.operation == "export" else restore_snapshot
    print(json.dumps({"operation": args.operation, "findings": operation(GraphDB(), args.graph, args.path)}))


if __name__ == "__main__":
    main()
