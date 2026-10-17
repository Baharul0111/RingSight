MATCH (d:Decision)-[:ON]->(pa:PendingAction)-[:BASED_ON]->(f:Finding)
WHERE f.id IN $ids
RETURN DISTINCT f.id AS finding_id,pa.id AS pending,d.decision AS decision
ORDER BY finding_id,pending
