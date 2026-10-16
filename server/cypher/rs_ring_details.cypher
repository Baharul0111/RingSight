MATCH (m:Account {{prop}:$cid})
OPTIONAL MATCH (m)-[t:TX]->(n:Account {{prop}:$cid}) WHERE t.ts<=$as_of
OPTIONAL MATCH (f:Finding)-[:ABOUT]->(m) WHERE f.typology IS NOT NULL AND f.expired_at IS NULL AND f.created_at<=$as_of
WITH m,count(DISTINCT t) AS t_n,count(DISTINCT f) AS f_n
RETURN $cid AS ring_id,$n AS size,
 collect({id:m.id,type:m.type,pagerank:m.pagerank,in_deg:m.in_deg,legit_hub:m.type IN ['merchant','payroll','exchange'],findings:f_n}) AS members,
 sum(t_n) AS internal_tx,sum(1.0/log(coalesce(m.in_deg,0)+5))/$n AS hub_weighted_density,
 toFloat(sum(CASE WHEN f_n>0 THEN 1 ELSE 0 END))/$n AS flagged_ratio
