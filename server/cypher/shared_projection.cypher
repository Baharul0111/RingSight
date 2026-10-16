// The loader materialises these exact weights from the generated identifier
// incidence lists; this query is the equivalent refresh after a data update.
MATCH (a:Account)-[:USES_DEVICE]->(d:Device)<-[:USES_DEVICE]-(b:Account)
WHERE a.id < b.id AND d.degree <= 10
WITH a, b, sum(1.0 / log(d.degree + 5)) AS w
MERGE (a)-[s:SHARES]->(b)
SET s.weight = coalesce(s.weight, 0) + w, s.kinds = coalesce(s.kinds, []) + ['device'], s.computed_at = $now;
MATCH (a:Account)-[s:SHARES]->(b:Account) WHERE s.weight >= 0.6
MERGE (a)-[t:SHARES_STRONG]->(b) SET t.weight = s.weight, t.kinds = s.kinds, t.computed_at = s.computed_at;
