MATCH (pa:PendingAction)-[:BASED_ON]->(f:Finding)
WHERE f.id IN $ids
RETURN DISTINCT f.id AS finding_id,pa.id AS pending,pa.kind AS kind,pa.status AS status
ORDER BY finding_id,pending
