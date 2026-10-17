// Each layer retains one actual route per reached account before expanding.
MATCH (n0:Account {id:$id})
WITH n0,[n0.id] AS path0,[] AS edges0
{expansions}
WITH n{hops} AS b,path{hops} AS path_ids,edges{hops} AS edges
WHERE b.id<>$id
RETURN b.id AS neighbour,b.type AS type,b.pagerank AS pagerank,{hops} AS hops,path_ids,edges
ORDER BY hops,neighbour LIMIT $limit
