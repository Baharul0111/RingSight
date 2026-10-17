MATCH (f:Finding)-[:ABOUT]->(e:{label})
WHERE e.id IN $ids AND f.created_at <= $as_of AND f.valid_from <= $as_of
  AND (f.expired_at IS NULL OR f.expired_at > $as_of)
  AND (f.valid_to IS NULL OR f.valid_to >= $as_of)
  AND ($inc OR f.reviewed)
RETURN properties(f) AS finding, f.created_at AS date_learned,
 collect(DISTINCT e.id) AS about
ORDER BY date_learned DESC LIMIT $limit
