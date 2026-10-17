// Exact, indexed transfer resolution. Future transfers never enter preflight.
MATCH (source:Account)-[t:TX {id:$q}]->(target:Account)
WHERE t.ts <= $as_of
RETURN 'Transfer' AS label, t.id AS id, 1.0 AS score, 'exact' AS how,
       source.id AS source, target.id AS target, t.amount AS amount,
       t.ts AS ts, t.rail AS rail, t.memo AS memo, 'TX' AS type
