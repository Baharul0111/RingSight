MATCH (e:{label}) WHERE e.id IN $ids
MATCH (f:Finding)-[:ABOUT]->(e)
WHERE f.created_at <= $as_of AND f.valid_from <= $as_of
  AND (f.expired_at IS NULL OR f.expired_at > $as_of)
  AND (f.valid_to IS NULL OR f.valid_to >= $as_of)
  AND ($inc OR f.reviewed)
RETURN f.id AS id, f.text AS text, f.typology AS typology, f.confidence AS confidence,
 f.author AS author, f.reviewed AS reviewed, f.created_at AS date_learned,
 f.valid_from AS valid_from, f.valid_to AS valid_to,
 f.evidence_tool_call_ids AS evidence_tool_call_ids, f.evidence_tx_ids AS evidence_tx_ids,
 collect(DISTINCT e.id) AS about
ORDER BY date_learned DESC LIMIT $limit
