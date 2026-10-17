"""No-model structural checks for deterministic synthetic data."""
import hashlib
import json
from collections import Counter

import pytest

from synth.generate import END, START, TYPOLOGIES, generate, write_dataset


@pytest.fixture(scope="module")
def dataset():
    return generate(1000, seed=42)


def test_all_planted_controls_survive_smallest_graph(dataset):
    assert len(dataset.nodes["Account"]) == 1000
    assert Counter(r["typology"] for r in dataset.rings) == {name: 5 for name in TYPOLOGIES}
    assert len(dataset.injections) == 20
    assert len(dataset.nodes["Restriction"]) == 3
    assert len(dataset.nodes["Alert"]) == 60
    assert len(dataset.name_variants) == 3
    assert {r["name"] for r in dataset.nodes["Rail"]} == {"UPI", "NEFT", "RTGS", "IMPS", "CARD", "WALLET"}
    assert len(dataset.nodes["IngestionDay"]) == 180 * 6
    mismatched = [d for d in dataset.nodes["IngestionDay"] if d["source_count"] != d["graph_count"]]
    assert len(mismatched) == 2 and all(d["rail"] == "IMPS" for d in mismatched)
    assert dataset.manifest["synthetic"] is True


def test_ids_and_external_only_truth(dataset):
    ids = [n.get("id", n.get("_key")) for rows in dataset.nodes.values() for n in rows]
    assert len(ids) == len(set(ids))
    graph_ids = set(ids)
    for rows in dataset.edges.values():
        for edge in rows:
            assert edge["_from"] in graph_ids and edge["_to"] in graph_ids
    assert {"ACC-4471", "ACC-10477", "ACC-55820", "ACC-7731"}.issubset(graph_ids)
    forbidden = {"is_sar", "is_laundering", "ground_truth", "planted", "typology"}
    assert not any(forbidden.intersection(row) for rows in [*dataset.nodes.values(), *dataset.edges.values()] for row in rows)
    assert all(START < t["ts"] <= END for t in dataset.edges["TX"])
    assert END - START + 1 == 180 * 86400


def test_cycles_are_chronological_and_decaying(dataset):
    transactions = {t["id"]: t for t in dataset.edges["TX"]}
    for ring in dataset.rings:
        if ring["typology"] != "cycle":
            continue
        edges = [transactions[tid] for tid in ring["tx_ids"]]
        assert 3 <= len(edges) <= 5
        assert all(a["ts"] < b["ts"] and a["amount"] >= b["amount"] >= a["amount"] * .8 for a, b in zip(edges, edges[1:]))
        assert edges[0]["_from"] == edges[-1]["_to"]


def test_hidden_exit_is_identifier_only(dataset):
    assert not any("ACC-55820" in (t["_from"], t["_to"]) for t in dataset.edges["TX"])
    device_uses = {t["_from"] for t in dataset.edges["USES_DEVICE"] if t["_to"] == "DEV-f31c"}
    assert device_uses == {"ACC-4471", "ACC-10477"}
    owned = {t["_to"] for t in dataset.edges["OWNS"] if t["_from"] == "PER-2291"}
    assert owned == {"ACC-10477", "ACC-55820"}


def test_injections_are_actual_memos_and_never_over_cap(dataset):
    transactions = {t["id"]: t for t in dataset.edges["TX"]}
    for attack in dataset.injections:
        assert transactions[attack["tx_id"]]["memo"] == attack["memo"]
        assert len(attack["memo"]) <= 80
    assert all(len(t.get("memo", "")) <= 80 for t in dataset.edges["TX"])


def test_deterministic_csvs_and_answer_keys(tmp_path, dataset):
    first = write_dataset(dataset, tmp_path / "first")
    second = write_dataset(generate(1000, seed=42), tmp_path / "second")
    assert first["csv_sha256"] == second["csv_sha256"]
    assert json.loads((tmp_path / "first" / "rings.json").read_text()) == dataset.rings
    assert "ring_id" not in (tmp_path / "first" / "Account.csv").read_text().splitlines()[0]


def test_invalid_tiny_graph_refused():
    with pytest.raises(ValueError):
        generate(100)


def test_demo_seed_has_no_shared_phone_shortcut_to_exit():
    from synth.generate import generate
    data=generate(accounts=1000)
    owners={e['_to']:e['_from'] for e in data.edges['OWNS']}
    assert owners['ACC-10477']==owners['ACC-55820']
    seed_phones={e['_to'] for e in data.edges['HAS_PHONE'] if e['_from']==owners['ACC-4471']}
    exit_phones={e['_to'] for e in data.edges['HAS_PHONE'] if e['_from']==owners['ACC-55820']}
    assert not seed_phones&exit_phones
