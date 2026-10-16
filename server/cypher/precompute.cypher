MATCH (a:Account)-[t:TX]->(b:Account) WITH a,b,sum(t.amount) AS amount,count(t) AS n,max(t.ts) AS last,min(t.ts) AS first MERGE (a)-[f:FLOW]->(b) SET f.id='FLOW-'+toString(id(a))+'-'+toString(id(b)),f.amount=amount,f.w=n,f.ts=last,f.first_ts=first,f.computed_at=$now;
CALL algo.pageRank('Account','TX') YIELD node, score SET node.pagerank = score;
CALL algo.betweenness({nodeLabels:['Account'], relationshipTypes:['TX'], samplingSize:256, samplingSeed:42}) YIELD node, score SET node.betweenness = score;
CALL algo.WCC({nodeLabels:['Account'], relationshipTypes:['TX']}) YIELD node, componentId SET node.wcc_id = componentId;
CALL algo.labelPropagation({nodeLabels:['Account'], relationshipTypes:['TX'], maxIterations:10}) YIELD node, communityId SET node.lpa_id = communityId;
CALL algo.WCC({nodeLabels:['Account'], relationshipTypes:['SHARES_STRONG']}) YIELD node, componentId SET node.ring_id = componentId;
MATCH (a:Account) SET a.algo_run_at = $now;
MATCH (a:Account) OPTIONAL MATCH (a)<-[i:TX]-() WITH a, count(i) AS n_in OPTIONAL MATCH (a)-[o:TX]->() WITH a, n_in, count(o) AS n_out SET a.in_deg = n_in, a.out_deg = n_out;
