MATCH (e:{label} {id:$id})
OPTIONAL MATCH (r:Restriction)-[:ON]->(e)
WHERE r.in_force_from<=$as_of AND (r.in_force_to IS NULL OR r.in_force_to >= $as_of)
WITH e,collect({id:r.id,kind:r.kind,from:r.in_force_from,to:r.in_force_to,source:r.source}) AS restrictions
{closure}
