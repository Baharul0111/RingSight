MATCH (e:{label}) WHERE e.id IN $ids
MATCH (f:Finding)-[:ABOUT]->(e)
WHERE f.created_at <= $as_of AND f.valid_from <= $as_of
  AND (f.expired_at IS NULL OR f.expired_at > $as_of)
  AND (f.valid_to IS NULL OR f.valid_to >= $as_of)
  AND ($inc OR f.reviewed)
OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Finding)
OPTIONAL MATCH (pa:PendingAction)-[:BASED_ON]->(f)
OPTIONAL MATCH (d:Decision)-[:ON]->(pa)
RETURN f.id AS id, f.text AS text, f.typology AS typology, f.confidence AS confidence,
 f.author AS author, f.reviewed AS reviewed, f.created_at AS date_learned,
 f.valid_from AS valid_from, f.valid_to AS valid_to, old.id AS supersedes,
 f.evidence_tool_call_ids AS evidence_tool_call_ids, f.evidence_tx_ids AS evidence_tx_ids,
 collect(DISTINCT {pending:pa.id,kind:pa.kind,status:pa.status,decision:d.decision}) AS actions,
 collect(DISTINCT e.id) AS about
ORDER BY date_learned DESC LIMIT $limit
