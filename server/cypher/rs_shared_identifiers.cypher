MATCH (a:Account {id:$id})-[u1:USES_DEVICE]->(d:Device)<-[u2:USES_DEVICE]-(b:Account)
WHERE b<>a AND d.degree<=$max_deg AND u1.first_seen<=$as_of AND u2.first_seen<=$as_of
RETURN b.id AS linked,'Account' AS kind,'soft' AS strength,1 AS hops,
 [a.id,d.id,b.id] AS path_ids,['USES_DEVICE','USES_DEVICE'] AS link_kinds,d.degree AS identifier_degree
LIMIT $limit
