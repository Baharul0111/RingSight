MATCH (src:Account)-[t1:TX]->(c:Account {id:$id})-[t2:TX]->(dst:Account)
WHERE t1.ts>$as_of-$win AND t1.ts<=$as_of AND t2.ts<=$as_of AND t1.ts<t2.ts AND t2.ts-t1.ts<=$win AND src<>dst AND src<>c AND dst<>c
WITH c,collect(DISTINCT src.id) AS sources,count(DISTINCT src) AS n_src,collect(DISTINCT dst.id) AS dests,count(DISTINCT dst) AS n_dst,
 collect(DISTINCT {id:t1.id,source:src.id,target:c.id,amount:t1.amount,ts:t1.ts,rail:t1.rail,memo:t1.memo,type:'TX'}) AS in_legs,
 collect(DISTINCT {id:t2.id,source:c.id,target:dst.id,amount:t2.amount,ts:t2.ts,rail:t2.rail,memo:t2.memo,type:'TX'}) AS out_legs
WHERE n_src >= $min AND n_dst >= $min
RETURN c.id AS collector,n_src,sources,n_dst,dests,in_legs[0..$limit] AS in_legs,out_legs[0..$limit] AS out_legs
