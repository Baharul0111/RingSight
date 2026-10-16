MATCH p=(a:Account {id:$id}){traversal}(b:Account)
WITH p,a,b,relationships(p) AS rs,nodes(p) AS ns
WHERE all(r IN rs WHERE r.ts>$from AND r.ts<=$as_of AND r.amount >= $min) AND b<>a
WITH b,length(p) AS hops,rs,ns ORDER BY hops,rs[0].ts
WITH b,min(hops) AS hops,head(collect(rs)) AS rs,head(collect(ns)) AS ns
RETURN b.id AS neighbour,b.type AS type,b.pagerank AS pagerank,hops,
 [n IN ns | n.id] AS path_ids,
 [i IN range(0,size(rs)-1) | {id:rs[i].id,amount:rs[i].amount,ts:rs[i].ts,rail:rs[i].rail,memo:rs[i].memo,source:startNode(rs[i]).id,target:endNode(rs[i]).id,type:'TX'}] AS edges
ORDER BY hops,neighbour LIMIT $limit
