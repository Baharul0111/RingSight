MATCH (s:Account {id:$src}),(d:Account {id:$dst})
MATCH p=(s)-[:{rels}*1..{hops}]->(d)
WITH p,relationships(p) AS rs,nodes(p) AS ns
WHERE all(r IN rs WHERE (type(r)='TX' AND r.ts<=$as_of AND r.ts>$from) OR (type(r)='SHARES_STRONG' AND r.computed_at<=$as_of))
RETURN [n IN ns | n.id] AS node_ids,
 [i IN range(0,size(rs)-1) | {id:rs[i].id,type:type(rs[i]),amount:rs[i].amount,ts:rs[i].ts,rail:rs[i].rail,memo:rs[i].memo,source:ns[i].id,target:ns[i+1].id}] AS edges,
 length(p) AS hops,reduce(w=0,r IN rs | w+coalesce(r.{weight},1)) AS pathWeight
ORDER BY pathWeight,hops LIMIT $limit
