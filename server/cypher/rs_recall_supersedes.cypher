// Optional context is read separately so absent actions cannot remove findings.
MATCH (f:Finding)-[:SUPERSEDES]->(old:Finding)
WHERE f.id IN $ids
RETURN f.id AS finding_id,old.id AS supersedes
ORDER BY finding_id,supersedes
