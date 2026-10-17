// Alert ids use ALERT-... in the generator. The target is a dated preflight anchor.
MATCH (e:Alert {id:$q})
WHERE e.raised_at <= $as_of
OPTIONAL MATCH (e)-[:ON]->(a:Account)
RETURN 'Alert' AS label, e.id AS id, 1.0 AS score, 'exact' AS how,
       e.raised_at AS raised_at, a.id AS account_id
