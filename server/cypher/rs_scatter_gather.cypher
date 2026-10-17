MATCH (s:Account {id:$id})-[t1:TX]->(m:Account)-[t2:TX]->(g:Account)
WHERE CASE WHEN t1.ts>$as_of-$win AND t1.ts<=$as_of AND t2.ts<=$as_of AND t1.ts<t2.ts AND t2.ts-t1.ts<=$win AND g<>s AND m<>g AND m<>s
 AND startNode(t1).id=$id AND endNode(t1).id=startNode(t2).id
 AND endNode(t1).id=m.id AND endNode(t2).id=g.id THEN true ELSE false END
WITH s,g,collect(DISTINCT m.id) AS mules,count(DISTINCT m) AS n_mules,
 collect({out_tx:t1.id,in_tx:t2.id,mule:endNode(t1).id,out_amt:t1.amount,in_amt:t2.amount,out_ts:t1.ts,in_ts:t2.ts,source:startNode(t1).id,gatherer:endNode(t2).id,out_rail:t1.rail,in_rail:t2.rail}) AS legs,
 collect(DISTINCT {id:t1.id,amount:t1.amount}) AS out_transfers,
 collect(DISTINCT {id:t2.id,amount:t2.amount}) AS in_transfers
WHERE n_mules >= $min
RETURN s.id AS source,g.id AS gatherer,n_mules,mules,legs[0..$limit] AS legs,
 reduce(total=0,leg IN out_transfers | total+leg.amount) AS scattered,
 reduce(total=0,leg IN in_transfers | total+leg.amount) AS gathered
ORDER BY n_mules DESC LIMIT $limit
