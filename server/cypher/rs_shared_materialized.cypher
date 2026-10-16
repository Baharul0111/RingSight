MATCH p=(a:Account {id:$id})-[:SHARES*1..{hops}]-(b:Account)
WITH p,a,b,relationships(p) AS rs,nodes(p) AS ns
WHERE b<>a AND all(s IN rs WHERE s.computed_at<=$as_of AND any(k IN s.kinds WHERE k IN $kinds))
WITH b,length(p) AS hops,rs,ns ORDER BY hops
WITH b,min(hops) AS hops,head(collect(rs)) AS rs,head(collect(ns)) AS ns
RETURN b.id AS linked,'Account' AS kind,hops,[n IN ns | n.id] AS path_ids,
 [s IN rs | {weight:s.weight,kinds:s.kinds}] AS link_kinds,reduce(w=1.0,s IN rs | w*s.weight) AS path_weight
ORDER BY hops,path_weight DESC LIMIT $limit
